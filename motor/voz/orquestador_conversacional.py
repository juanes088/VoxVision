import logging
from pathlib import Path

import numpy as np
from PIL import Image

from motor.configuracion import Configuracion
from motor.percepcion.buffer_visual import BufferVisual
from motor.percepcion.captador_percepcion import CaptadorPercepcion
from motor.vision.gestor_inferencia import GestorInferencia
from motor.voz.capturador_audio import CapturadorAudio
from motor.voz.texto_voz import limpiar_para_voz
from motor.voz.conversador_claude import ConversadorClaude
from motor.voz.conversador_qwen import ConversadorQwen
from motor.voz.sintetizador_piper import SintetizadorPiper
from motor.voz.transcritor_whisper import TranscriptorWhisper

registro = logging.getLogger(__name__)

# Palabras que sugieren que la pregunta mira al pasado. Cuando aparecen, se
# adjuntan keyframes (escalón lento) además del resumen de texto.
_PISTAS_PASADO = (
    "antes", "hace un rato", "hace rato", "estaba", "estabas", "hiciste",
    "viste", "habia", "había", "hace un momento", "recien", "recién",
    "anteriormente", "que hice", "qué hice", "que hacia", "qué hacía",
)


class OrquestadorConversacional:
    """
    Orquesta el flujo completo de conversación con visión:
    Audio → Transcripción → Conversación con visión → Síntesis de voz
    """

    def __init__(
        self,
        configuracion: Configuracion,
        gestor: GestorInferencia,
        sintetizador: SintetizadorPiper,
    ):
        self.configuracion = configuracion
        self.gestor = gestor
        
        # Componentes de voz
        self.capturador = CapturadorAudio(
            frecuencia_muestreo=16000,
            canales=1,
            duracion_chunk_segundos=0.5,
        )
        self.transcritor = TranscriptorWhisper(configuracion, gestor)
        # Proveedor de vision+conversacion segun configuracion.
        # Proveedor conmutable en caliente. Se cachean las instancias para no
        # recrearlas (y conservar su historial) al alternar.
        self._cache_conversadores: dict = {}
        self.proveedor_actual = configuracion.proveedor_vision
        self.conversador = self._obtener_conversador(self.proveedor_actual)
        self.sintetizador = sintetizador

        # Memoria visual de corto plazo (en RAM) y captioner de fondo.
        self.buffer_visual = BufferVisual(
            ventana_segundos=configuracion.percepcion_ventana_segundos,
            max_frames=configuracion.percepcion_max_frames,
        )
        # "B sola": el captor solo guarda escenas (sin captions de texto) salvo
        # que se reactive la "C" por configuracion.
        describir = (
            self.conversador.describir_escena
            if configuracion.percepcion_captions_texto
            else None
        )
        self.captador = CaptadorPercepcion(
            buffer=self.buffer_visual,
            describir_escena=describir,
            fps=configuracion.percepcion_fps,
            umbral_cambio=configuracion.percepcion_umbral_cambio,
        )
        if configuracion.percepcion_activa:
            self.captador.iniciar()

        # Estado
        self._ultimo_frame: Image.Image | None = None
        # Frames elegidos por la interfaz para la proxima consulta (hasta 3).
        self._frames_consulta: list[Image.Image] = []
        self._directorio_audio = Path("almacenamiento/audio")
        self._directorio_audio.mkdir(parents=True, exist_ok=True)
        self._contador_interacciones = 0

    def _crear_conversador(self, nombre: str):
        if nombre == "claude":
            return ConversadorClaude(self.configuracion)
        return ConversadorQwen(self.configuracion, self.gestor)

    def _obtener_conversador(self, nombre: str):
        if nombre not in self._cache_conversadores:
            self._cache_conversadores[nombre] = self._crear_conversador(nombre)
            registro.info("Conversador creado: %s", nombre)
        return self._cache_conversadores[nombre]

    def establecer_proveedor(self, nombre: str) -> str:
        """Cambia el proveedor de vision en caliente. Devuelve el activo."""
        nombre = nombre if nombre in ("claude", "local") else "local"
        self.proveedor_actual = nombre
        self.conversador = self._obtener_conversador(nombre)
        registro.info("Proveedor de vision activo: %s", nombre)
        return nombre

    def actualizar_frame(self, frame: Image.Image) -> None:
        """Actualiza el frame actual de la cámara para contexto visual."""
        self._ultimo_frame = frame
        # El captor decide (a su ritmo) si vale la pena describir la escena.
        self.captador.actualizar_frame(frame)

    def actualizar_frames(self, imagenes: list[Image.Image]) -> None:
        """Registra los keyframes elegidos por la interfaz para la consulta."""
        self._frames_consulta = imagenes[:3]
        if imagenes:
            self._ultimo_frame = imagenes[-1]

    def _imagenes_consulta(self) -> list[Image.Image]:
        """
        Frames a enviar. En modo local el 3B no aguanta varias imagenes en 8GB,
        asi que se envia solo la ultima; por API se envian hasta 3.
        """
        frames = self._frames_consulta or (
            [self._ultimo_frame] if self._ultimo_frame is not None else []
        )
        if self.proveedor_actual == "local":
            return frames[-1:]          # el 3B solo aguanta 1 imagen en 8GB
        return frames[:5]               # Claude (API): hasta 5

    def iniciar_escucha(self) -> None:
        """Inicia la captura de audio del micrófono."""
        self.capturador.iniciar_grabacion()
        registro.info("Escuchando...")

    def detener_y_procesar(self) -> tuple[str, str, Path]:
        """
        Detiene la captura de audio y procesa la conversación completa.
        
        Returns:
            Tupla con (transcripción, respuesta_texto, ruta_audio_respuesta)
        """
        # Detener captura y obtener audio
        audio = self.capturador.detener_grabacion()
        
        if len(audio) == 0:
            registro.warning("No se capturó audio")
            return "", "", Path()
        
        # Guardar audio capturado (opcional, para debugging)
        self._contador_interacciones += 1
        ruta_audio_entrada = self._directorio_audio / f"entrada_{self._contador_interacciones:04d}.wav"
        self.capturador.guardar_audio(audio, ruta_audio_entrada)
        
        # Transcribir
        registro.info("Transcribiendo audio...")
        transcripcion = self.transcritor.transcribir(audio, idioma="es")
        
        if not transcripcion:
            registro.warning("Transcripción vacía")
            return "", "", Path()
        
        registro.info("Usuario dijo: '%s'", transcripcion)
        
        # Conversar con los keyframes elegidos (hasta 3, resolucion completa).
        registro.info("Generando respuesta con contexto visual...")
        imagenes = self._imagenes_consulta()
        respuesta = self.conversador.conversar(
            texto_usuario=transcripcion,
            imagen=None,
            imagenes_pasado=imagenes,
        )
        self._frames_consulta = []  # se consumen en esta consulta

        registro.info("Asistente responde: '%s'", respuesta)
        
        # Sintetizar respuesta: se limpia el markdown para que la voz no diga
        # "asterisco" ni "slash"; el texto original (con formato) se devuelve
        # para mostrarlo en el chat.
        registro.info("Sintetizando voz...")
        ruta_audio_salida = self._directorio_audio / f"salida_{self._contador_interacciones:04d}.wav"
        self.sintetizador.sintetizar(limpiar_para_voz(respuesta), ruta_audio_salida)

        return transcripcion, respuesta, ruta_audio_salida

    def procesar_texto_directo(self, texto: str, incluir_vision: bool = True) -> tuple[str, Path]:
        """
        Procesa texto directamente sin captura de audio (útil para testing o chat).
        
        Args:
            texto: Texto del usuario
            incluir_vision: Si incluir el frame actual como contexto
            
        Returns:
            Tupla con (respuesta_texto, ruta_audio_respuesta)
        """
        self._contador_interacciones += 1

        # Conversar (chat por texto: usa el ultimo frame disponible).
        imagenes = self._imagenes_consulta() if incluir_vision else []
        respuesta = self.conversador.conversar(
            texto_usuario=texto,
            imagen=None,
            imagenes_pasado=imagenes,
        )
        
        # Sintetizar (voz sin markdown; ver detener_y_procesar).
        ruta_audio_salida = self._directorio_audio / f"salida_{self._contador_interacciones:04d}.wav"
        self.sintetizador.sintetizar(limpiar_para_voz(respuesta), ruta_audio_salida)

        return respuesta, ruta_audio_salida

    def esta_escuchando(self) -> bool:
        """Verifica si está capturando audio actualmente."""
        return self.capturador.esta_grabando()

    def _contexto_para(self, texto: str) -> tuple[str, list[Image.Image]]:
        """
        Modo simple: la conversación usa solo el frame actual. Sin memoria
        visual ni montaje. (El experimento de varios frames queda tras la
        bandera percepcion_activa por si se quiere reactivar.)
        """
        if not self.configuracion.percepcion_activa:
            return "", []

        imagenes_pasado: list[Image.Image] = []
        texto_normalizado = texto.lower()
        if any(pista in texto_normalizado for pista in _PISTAS_PASADO):
            montaje = self.buffer_visual.montaje_pasado(
                cantidad=self.configuracion.percepcion_keyframes_pasado,
                columnas=self.configuracion.percepcion_montaje_columnas,
                lado_celda=self.configuracion.percepcion_montaje_lado_celda,
            )
            if montaje is not None:
                imagenes_pasado = [montaje]
        return "", imagenes_pasado

    def limpiar_historial(self) -> None:
        """Limpia el historial de conversación y la memoria visual reciente."""
        self.conversador.limpiar_historial()
        self.buffer_visual.limpiar()
        registro.info("Historial limpiado")

    def limpiar(self) -> None:
        """Limpia recursos."""
        self.captador.detener()
        self.capturador.limpiar()
