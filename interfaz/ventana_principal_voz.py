import html
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import cv2
from PySide6.QtCore import QSize, QTimer, Qt, QUrl
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from interfaz.cliente_motor import ClienteMotor
from interfaz.configuracion import ConfiguracionInterfaz
from interfaz.onda_audio import OndaAudio
from interfaz.panel_seleccion import PanelFramesSeleccionados
from interfaz.seleccion_frames import seleccionar_keyframes
from interfaz.tira_frames import TiraFrames

# Captura durante la intervencion: ~4 fps para no perder momentos breves
# (mostrar el celular un segundo). El motor luego recorta segun el proveedor.
_INTERVALO_CAPTURA_S = 0.25
_MAX_FRAMES_INTERVENCION = 90
_MAX_KEYFRAMES = 5  # keyframes por clustering; el motor limita segun proveedor


class VentanaPrincipal(QMainWindow):
    def __init__(self, configuracion: ConfiguracionInterfaz):
        super().__init__()
        self.configuracion = configuracion
        self.cliente = ClienteMotor(configuracion.url_motor)
        self.ejecutor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="visual_memory")
        self.captura = cv2.VideoCapture(configuracion.indice_camara, cv2.CAP_DSHOW)
        self.futuro_envio: Future | None = None
        self.futuro_consulta: Future | None = None
        self.ultimo_jpeg: bytes | None = None
        self._ultimo_frame_rgb = None
        self._contador_ms = 0

        # Captura por intervencion (micro on -> off) y seleccion de keyframes.
        self._frames_intervencion: list = []
        self._indices_seleccion: list[int] = []
        self._ultima_captura_s = 0.0
        
        # Componentes de voz
        self._grabando_voz = False
        self._player_audio = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player_audio.setAudioOutput(self._audio_output)
        self._player_audio.playbackStateChanged.connect(self._estado_reproduccion)

        self._construir_interfaz()
        self._configurar_temporizadores()

    def _construir_interfaz(self) -> None:
        self.setWindowTitle("Visual Memory - Asistente Conversacional")
        self.resize(1400, 900)

        contenedor = QWidget()
        disposicion_principal = QVBoxLayout(contenedor)
        disposicion_principal.setContentsMargins(16, 16, 16, 16)
        disposicion_principal.setSpacing(10)

        titulo = QLabel("Asistente conversacional con visión")
        titulo.setObjectName("titulo")
        disposicion_principal.addWidget(titulo)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(14)

        self.video = QLabel("Esperando cámara...")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(640, 480)
        self.video.setObjectName("video")
        cuerpo.addWidget(self.video, 3)

        panel_chat = QVBoxLayout()
        panel_chat.setSpacing(10)

        # Cabecera del chat: titulo + estado (Escuchando/Pensando/Respuesta).
        fila_cabecera = QHBoxLayout()
        etiqueta_chat = QLabel("Conversación")
        etiqueta_chat.setObjectName("etiqueta_chat")
        self.estado_conversacion = QLabel("")
        self.estado_conversacion.setObjectName("estado_conversacion")
        self.estado_conversacion.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        fila_cabecera.addWidget(etiqueta_chat)
        fila_cabecera.addStretch()
        fila_cabecera.addWidget(self.estado_conversacion)

        self.historial = QTextEdit()
        self.historial.setReadOnly(True)
        self.historial.setPlaceholderText("Las conversaciones aparecerán aquí...")

        # Tira visual de seleccion de frames (bajo el chat, sobre el boton).
        self.tira = TiraFrames()
        self.tira.seleccion_terminada.connect(self._tras_seleccion)

        # Controles de voz
        fila_voz = QHBoxLayout()

        self.boton_voz = QPushButton("Hablar por audio")
        self.boton_voz.setObjectName("boton_voz")
        self.boton_voz.setMinimumHeight(60)
        self.boton_voz.setCheckable(True)  # Hacer el botón tipo toggle
        self.boton_voz.clicked.connect(self._toggle_grabacion_voz)

        ruta_icono = Path(__file__).parent / "estilos" / "microfono.svg"
        self._icono_voz = QIcon(str(ruta_icono)) if ruta_icono.exists() else QIcon()
        self.boton_voz.setIcon(self._icono_voz)
        self.boton_voz.setIconSize(QSize(18, 18))

        # Onda de audio: va DENTRO del boton (overlay), no como franja aparte.
        self.onda = OndaAudio(self.boton_voz)

        fila_voz.addWidget(self.boton_voz)

        # Controles: solo el selector de modo (sistema 100% por voz).
        fila_controles = QHBoxLayout()
        etiqueta_modo = QLabel("Modo:")
        self.combo_proveedor = QComboBox()
        self.combo_proveedor.addItem("API", "claude")
        self.combo_proveedor.addItem("Local", "local")
        self.combo_proveedor.currentIndexChanged.connect(self._cambiar_proveedor)

        fila_controles.addStretch()
        fila_controles.addWidget(etiqueta_modo)
        fila_controles.addWidget(self.combo_proveedor)

        panel_chat.addLayout(fila_cabecera)
        panel_chat.addWidget(self.historial, 1)
        panel_chat.addWidget(self.tira)
        panel_chat.addLayout(fila_voz)
        panel_chat.addLayout(fila_controles)

        cuerpo.addLayout(panel_chat, 2)
        disposicion_principal.addLayout(cuerpo, 1)

        self.estado = QLabel("Motor: comprobando...")
        self.estado.setObjectName("estado")
        disposicion_principal.addWidget(self.estado)

        self.setCentralWidget(contenedor)

        # Popup central de "Frames seleccionados" (overlay sobre toda la ventana).
        self._contenedor_central = contenedor
        self.panel_seleccion = PanelFramesSeleccionados(contenedor)
        self.tira.reveal_listo.connect(self.panel_seleccion.mostrar)

        self.setStyleSheet(self._estilos())

    def _configurar_temporizadores(self) -> None:
        # Cámara a 30 FPS (más fluido)
        self.temporizador_camara = QTimer(self)
        self.temporizador_camara.timeout.connect(self._actualizar_camara)
        self.temporizador_camara.start(33)

        self.temporizador_tareas = QTimer(self)
        self.temporizador_tareas.timeout.connect(self._revisar_tareas)
        self.temporizador_tareas.start(100)

        # Estado del motor cada 10 segundos (menos frecuente = más rápido)
        self.temporizador_estado = QTimer(self)
        self.temporizador_estado.timeout.connect(self._comprobar_motor)
        self.temporizador_estado.start(10000)
        self._comprobar_motor()

        # Ya NO se envian frames en continuo. La voz manda sus keyframes al
        # soltar el boton; el chat por texto manda el frame actual bajo demanda.

        # Indicador de memoria visual cada 2 segundos (no bloqueante).
        self.temporizador_memoria = QTimer(self)
        self.temporizador_memoria.timeout.connect(self._consultar_memoria)
        self.temporizador_memoria.start(2000)

    def _actualizar_camara(self) -> None:
        ret, frame = self.captura.read()
        if not ret:
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        altura, ancho, canales = frame_rgb.shape
        bytes_por_linea = canales * ancho
        imagen_qt = QImage(frame_rgb.data, ancho, altura, bytes_por_linea, QImage.Format_RGB888)
        self.video.setPixmap(QPixmap.fromImage(imagen_qt).scaled(
            self.video.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        ))

        # Guardar último frame como JPEG para enviar al motor
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        self.ultimo_jpeg = buffer.tobytes()
        self._ultimo_frame_rgb = frame_rgb

        # Durante la grabación, muestrear frames para la seleccion posterior.
        if self._grabando_voz:
            self._quiza_capturar_intervencion(frame_rgb)

    def _quiza_capturar_intervencion(self, frame_rgb) -> None:
        """Guarda un frame de la intervencion cada ~0.5s y lo pinta en la tira."""
        ahora = time.monotonic()
        if ahora - self._ultima_captura_s < _INTERVALO_CAPTURA_S:
            return
        if len(self._frames_intervencion) >= _MAX_FRAMES_INTERVENCION:
            return
        self._ultima_captura_s = ahora
        self._frames_intervencion.append(frame_rgb.copy())

        altura, ancho, canales = frame_rgb.shape
        imagen_qt = QImage(
            frame_rgb.data, ancho, altura, canales * ancho, QImage.Format_RGB888
        )
        # Pixmap grande: la tira lo muestra pequeno en captura y grande en el reveal.
        miniatura = QPixmap.fromImage(imagen_qt).scaled(
            180, 135, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.tira.agregar_miniatura(miniatura)

    def _enviar_frame_contexto(self) -> None:
        """Envía el frame actual al motor para contexto visual."""
        if self.ultimo_jpeg is None:
            return
        
        if self.futuro_envio is not None and not self.futuro_envio.done():
            return
        
        self.futuro_envio = self.ejecutor.submit(
            self.cliente.actualizar_frame_contexto,
            self.ultimo_jpeg,
        )

    def _toggle_grabacion_voz(self, checked: bool) -> None:
        """Toggle para iniciar/detener grabación con un solo clic."""
        if checked:
            # Iniciar grabación: reiniciar la captura por intervencion.
            self._grabando_voz = True
            self._frames_intervencion = []
            self._ultima_captura_s = 0.0
            self.tira.limpiar()
            # Barge-in: si el asistente esta hablando, cortar su respuesta.
            self._player_audio.stop()
            self.boton_voz.setText("Detener grabación")
            self._marcar_grabando(True)
            self._fijar_estado("Escuchando")

            # Iniciar captura de audio
            try:
                self.cliente.iniciar_escucha()
            except Exception as e:
                self._mostrar_error(f"Error iniciando grabación: {str(e)}")
                self.boton_voz.setChecked(False)
                self._grabando_voz = False
        else:
            # Detener grabación: seleccionar keyframes y animar. El montaje se
            # arma y se envia en _tras_seleccion, al terminar la animacion.
            self._grabando_voz = False
            self.boton_voz.setText("Procesando...")
            self._marcar_grabando(False)
            self.boton_voz.setEnabled(False)
            self._fijar_estado("Pensando")

            self._indices_seleccion = seleccionar_keyframes(
                self._frames_intervencion, maximo=_MAX_KEYFRAMES
            )
            self.tira.animar_seleccion(self._indices_seleccion)

    def _marcar_grabando(self, activo: bool) -> None:
        """Boton rojo + onda de ecualizador DENTRO del boton mientras se graba."""
        self.boton_voz.setProperty("grabando", "true" if activo else "false")
        estilo = self.boton_voz.style()
        estilo.unpolish(self.boton_voz)
        estilo.polish(self.boton_voz)
        if activo:
            # Ocultar texto/icono y poner la onda ocupando el boton.
            self.boton_voz.setText("")
            self.boton_voz.setIcon(QIcon())
            self.onda.setGeometry(self.boton_voz.rect())
            self.onda.iniciar()
        else:
            self.onda.detener()
            self.boton_voz.setIcon(self._icono_voz)

    def _tras_seleccion(self) -> None:
        """Al terminar la animacion: elige el frame nitido y lanza la conversacion."""
        seleccionados = [
            self._frames_intervencion[i]
            for i in self._indices_seleccion
            if 0 <= i < len(self._frames_intervencion)
        ]
        self.futuro_consulta = self.ejecutor.submit(
            self._enviar_frame_y_procesar, seleccionados
        )

    def _enviar_frame_y_procesar(self, frames: list) -> None:
        """
        Envia al motor los keyframes relevantes (hasta 3) a resolucion completa,
        como imagenes separadas. Varios momentos aumentan la probabilidad de que
        el objeto mostrado quede bien capturado en al menos uno.
        """
        try:
            jpegs = []
            for frame in frames[:5]:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                ok, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if ok:
                    jpegs.append(buffer.tobytes())
            if jpegs:
                self.cliente.actualizar_frames_contexto(jpegs)
            elif self.ultimo_jpeg:
                self.cliente.actualizar_frames_contexto([self.ultimo_jpeg])
        except Exception as error:  # noqa: BLE001
            print(f"Error enviando frames: {error}")
        self._procesar_conversacion_voz()

    def _iniciar_grabacion_voz(self) -> None:
        """DEPRECATED: Mantener por compatibilidad."""
        pass

    def _detener_grabacion_voz(self) -> None:
        """DEPRECATED: Mantener por compatibilidad."""
        pass

    def _procesar_conversacion_voz(self) -> None:
        """Procesa la conversación por voz (transcripción + respuesta + síntesis)."""
        try:
            resultado = self.cliente.detener_y_procesar()
            
            if not resultado or "transcripcion" not in resultado:
                self._mostrar_error("No se pudo procesar el audio")
                return
            
            transcripcion = resultado["transcripcion"]
            respuesta = resultado["respuesta"]
            ruta_audio = resultado.get("ruta_audio", "")
            
            if not transcripcion:
                self._mostrar_mensaje("No se detectó audio. Intenta de nuevo.")
                return
            
            # Mostrar en historial
            self.historial.append(f"<b style='color: #111111;'>Tú:</b> {html.escape(transcripcion)}")
            self.historial.append(
            f"<b style='color: #444444;'>Asistente:</b> {self._formato_respuesta(respuesta)}"
        )
            self.historial.append("<hr>")
            
            # Reproducir audio de respuesta
            self._fijar_estado("Respuesta")
            if ruta_audio:
                self._reproducir_audio(ruta_audio)
            else:
                self._fijar_estado("")

        except Exception as e:
            self._mostrar_error(f"Error en conversación: {str(e)}")
            self._fijar_estado("")
        finally:
            self.boton_voz.setText("Hablar por audio")
            self.boton_voz.setEnabled(True)
            self.boton_voz.setChecked(False)
            self._marcar_grabando(False)

    def _fijar_estado(self, texto: str) -> None:
        """Actualiza el indicador Escuchando / Pensando / Respuesta."""
        self.estado_conversacion.setText(texto)

    def _estado_reproduccion(self, estado) -> None:
        """Limpia el estado 'Respuesta' cuando termina de reproducirse el audio."""
        if estado == QMediaPlayer.PlaybackState.StoppedState:
            if self.estado_conversacion.text() == "Respuesta":
                self.estado_conversacion.setText("")

    def _reproducir_audio(self, ruta: str) -> None:
        """Reproduce el audio de respuesta."""
        try:
            # Convertir ruta WSL a Windows si es necesario
            if ruta.startswith("almacenamiento/"):
                ruta_completa = Path("C:/VisualMemory") / ruta
            else:
                ruta_completa = Path(ruta)
            
            if ruta_completa.exists():
                self._player_audio.setSource(QUrl.fromLocalFile(str(ruta_completa)))
                self._player_audio.play()
        except Exception as e:
            print(f"Error reproduciendo audio: {e}")

    def _cambiar_proveedor(self, _indice: int) -> None:
        """Cambia el proveedor de vision del motor (no bloqueante)."""
        modo = self.combo_proveedor.currentData()
        self.historial.append(
            f"<i style='color: #888;'>Cambiando a modo: {self.combo_proveedor.currentText()}...</i>"
        )
        self.ejecutor.submit(self._aplicar_proveedor, modo)

    def _aplicar_proveedor(self, modo: str) -> None:
        try:
            self.cliente.establecer_proveedor(modo)
        except Exception as error:  # noqa: BLE001
            print(f"Error cambiando proveedor: {error}")

    def _sincronizar_proveedor(self, proveedor: str) -> None:
        """Refleja el proveedor activo del motor en el combo, sin re-enviar."""
        indice = self.combo_proveedor.findData(proveedor)
        if indice >= 0 and indice != self.combo_proveedor.currentIndex():
            self.combo_proveedor.blockSignals(True)
            self.combo_proveedor.setCurrentIndex(indice)
            self.combo_proveedor.blockSignals(False)

    def _comprobar_motor(self) -> None:
        """Comprueba el estado del motor (sin bloquear)."""
        # Ejecutar en segundo plano para no bloquear la interfaz
        def _verificar():
            try:
                estado = self.cliente.obtener_estado()
                return True if estado else False
            except:
                return False
        
        # Si ya hay una verificación en curso, saltar
        if hasattr(self, '_futuro_verificacion') and self._futuro_verificacion and not self._futuro_verificacion.done():
            return
        
        self._futuro_verificacion = self.ejecutor.submit(_verificar)

    def _consultar_memoria(self) -> None:
        """Consulta el estado de la memoria visual (sin bloquear)."""
        if getattr(self, "_futuro_memoria", None) is not None and not self._futuro_memoria.done():
            return

        def _consultar():
            return self.cliente.obtener_estado_voz()

        self._futuro_memoria = self.ejecutor.submit(_consultar)

    def _revisar_tareas(self) -> None:
        """Revisa tareas en segundo plano."""
        # Revisar verificación del motor
        if hasattr(self, '_futuro_verificacion') and self._futuro_verificacion and self._futuro_verificacion.done():
            try:
                conectado = self._futuro_verificacion.result()
                if conectado:
                    self.estado.setText("Motor: conectado")
                    self.estado.setStyleSheet("color: #2e7d32;")
                else:
                    self.estado.setText("Motor: desconectado")
                    self.estado.setStyleSheet("color: #b00020;")
            except:
                self.estado.setText("Motor: error")
                self.estado.setStyleSheet("color: #b00020;")
            finally:
                self._futuro_verificacion = None

        # Sincronizar el modo (proveedor) con el estado del motor.
        if getattr(self, "_futuro_memoria", None) is not None and self._futuro_memoria.done():
            try:
                estado_voz = self._futuro_memoria.result()
                proveedor = estado_voz.get("proveedor")
                if proveedor:
                    self._sincronizar_proveedor(proveedor)
            except Exception:
                pass
            finally:
                self._futuro_memoria = None

        # Revisar consultas
        if self.futuro_consulta is not None and self.futuro_consulta.done():
            try:
                self.futuro_consulta.result()
            except Exception as e:
                print(f"Error en tarea: {e}")
            finally:
                self.futuro_consulta = None

    @staticmethod
    def _formato_respuesta(texto: str) -> str:
        """Convierte el markdown del modelo en HTML (negrita, vinetas) para el chat."""
        t = html.escape(texto)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
        t = re.sub(r"(?m)^[ \t]*[-*]\s+", "• ", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        t = t.replace("*", "")  # asteriscos sueltos restantes
        return t.replace("\n", "<br>")

    def _mostrar_error(self, mensaje: str) -> None:
        """Muestra un mensaje de error."""
        self.historial.append(f"<b style='color: #b00020;'>Error:</b> {mensaje}")

    def _mostrar_mensaje(self, mensaje: str) -> None:
        """Muestra un mensaje informativo."""
        self.historial.append(f"<i style='color: #888;'>{mensaje}</i>")

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        panel = getattr(self, "panel_seleccion", None)
        if panel is not None and panel.isVisible():
            panel.setGeometry(self._contenedor_central.rect())

    def closeEvent(self, evento) -> None:
        """Limpia recursos al cerrar."""
        self.temporizador_camara.stop()
        self.temporizador_tareas.stop()
        self.temporizador_estado.stop()
        self.temporizador_memoria.stop()
        self.captura.release()
        self.ejecutor.shutdown(wait=False)
        evento.accept()

    def _estilos(self) -> str:
        """Carga la hoja de estilos minimalista desde archivo (.qss)."""
        ruta_qss = Path(__file__).parent / "estilos" / "minimalista.qss"
        try:
            return ruta_qss.read_text(encoding="utf-8")
        except OSError:
            return ""
