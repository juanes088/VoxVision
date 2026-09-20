"""
Tira visual de frames.

Durante la captura muestra las miniaturas (con scroll). Al elegir, anima la
seleccion EN SITIO: las descartadas se atenuan (gris) y las elegidas se
resaltan (verde). Al terminar emite `reveal_listo` con los frames elegidos
para el popup central. La conversacion arranca al instante (no espera).
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_MINI_W, _MINI_H = 96, 72


class TiraFrames(QWidget):
    seleccion_terminada = Signal()      # arrancar el envio al motor
    reveal_listo = Signal(list)         # pixmaps elegidos, para el popup

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._miniaturas: list[QLabel] = []
        self._pixmaps: list[QPixmap] = []
        self._efectos: list[QGraphicsOpacityEffect] = []
        self._indices: set[int] = set()
        self._paso = 0
        self._temporizador = QTimer(self)
        self._temporizador.timeout.connect(self._animar_paso)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(4)

        self.titulo = QLabel("Frames capturados")
        self.titulo.setObjectName("titulo_tira")
        raiz.addWidget(self.titulo)

        self._area = QScrollArea()
        self._area.setObjectName("area_tira")
        self._area.setWidgetResizable(True)
        self._area.setFixedHeight(_MINI_H + 20)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        contenedor = QWidget()
        self._fila = QHBoxLayout(contenedor)
        self._fila.setContentsMargins(6, 4, 6, 4)
        self._fila.setSpacing(6)
        self._fila.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._area.setWidget(contenedor)
        raiz.addWidget(self._area)

    def limpiar(self) -> None:
        self._temporizador.stop()
        while self._fila.count():
            item = self._fila.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._miniaturas.clear()
        self._pixmaps.clear()
        self._efectos.clear()
        self._indices.clear()
        self._paso = 0
        self.titulo.setText("Frames capturados")

    def agregar_miniatura(self, pixmap: QPixmap) -> None:
        self._pixmaps.append(pixmap)
        etiqueta = QLabel()
        etiqueta.setObjectName("miniatura")
        etiqueta.setFixedSize(_MINI_W, _MINI_H)
        etiqueta.setScaledContents(True)
        etiqueta.setPixmap(pixmap)
        efecto = QGraphicsOpacityEffect(etiqueta)
        efecto.setOpacity(1.0)
        etiqueta.setGraphicsEffect(efecto)
        self._fila.addWidget(etiqueta)
        self._miniaturas.append(etiqueta)
        self._efectos.append(efecto)
        self.titulo.setText(f"Frames capturados: {len(self._miniaturas)}")

    def animar_seleccion(self, indices_elegidos: list[int]) -> None:
        # Arranca el envio ya; la animacion es solo visual.
        self.seleccion_terminada.emit()
        self._indices = {i for i in indices_elegidos if 0 <= i < len(self._miniaturas)}
        self._paso = 0
        if not self._miniaturas:
            return
        self.titulo.setText("Eligiendo frames relevantes...")
        paso = max(25, int(1100 / len(self._miniaturas)))
        self._temporizador.start(paso)

    def _animar_paso(self) -> None:
        indice = self._paso
        if indice >= len(self._miniaturas):
            self._temporizador.stop()
            self.titulo.setText(f"Frames elegidos: {len(self._indices)}")
            pixmaps = [self._pixmaps[i] for i in sorted(self._indices)]
            self.reveal_listo.emit(pixmaps)
            return

        etiqueta = self._miniaturas[indice]
        if indice in self._indices:
            etiqueta.setStyleSheet("border: 2px solid #107c10; border-radius: 3px;")
            self._efectos[indice].setOpacity(1.0)
        else:
            etiqueta.setStyleSheet("border: 1px solid #d0d0d0; border-radius: 3px;")
            self._efectos[indice].setOpacity(0.35)
        # Auto-scroll: la tira sigue el frame que se esta evaluando.
        self._area.ensureWidgetVisible(etiqueta, 60, 0)
        self._paso += 1
