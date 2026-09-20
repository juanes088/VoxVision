"""
Onda de audio animada, pensada como OVERLAY dentro del boton de grabar.

Dibuja barras blancas centradas que "laten" como un ecualizador mientras se
graba. Es transparente al mouse (los clics pasan al boton para detener).
"""
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

_BARRAS = 18
_COLOR = QColor("#ffffff")


class OndaAudio(QWidget):
    """Barras tipo ecualizador; visible solo mientras se graba."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("onda_audio")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._fase = 0.0
        self._temporizador = QTimer(self)
        self._temporizador.timeout.connect(self._tick)
        self.hide()

    def iniciar(self) -> None:
        self.show()
        self.raise_()
        self._temporizador.start(45)

    def detener(self) -> None:
        self._temporizador.stop()
        self.hide()

    def _tick(self) -> None:
        self._fase += 0.35
        self.update()

    def paintEvent(self, _evento) -> None:
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.Antialiasing, True)
        pintor.setPen(Qt.NoPen)
        pintor.setBrush(_COLOR)

        ancho = self.width()
        alto = self.height()
        centro_y = alto / 2
        hueco = 4
        ancho_barra = 3.0
        ancho_total = _BARRAS * ancho_barra + (_BARRAS - 1) * hueco
        inicio_x = (ancho - ancho_total) / 2
        alto_max = alto * 0.5

        for i in range(_BARRAS):
            onda = (
                math.sin(self._fase + i * 0.5) * 0.5
                + math.sin(self._fase * 0.6 + i * 0.9) * 0.5
            )
            magnitud = 0.22 + 0.78 * abs(onda)
            alto_barra = max(3.0, magnitud * alto_max)
            x = inicio_x + i * (ancho_barra + hueco)
            y = centro_y - alto_barra / 2
            pintor.drawRoundedRect(
                int(x), int(y), int(ancho_barra), int(alto_barra), 1, 1
            )
        pintor.end()
