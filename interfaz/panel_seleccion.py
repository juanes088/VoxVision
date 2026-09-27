"""
Popup central que muestra los frames seleccionados por ~3 segundos.

Cubre la ventana con un fondo translucido y una tarjeta centrada con los
frames elegidos. Aparece con fundido ("pum"), espera 3s y se desvanece.
"""
from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

_SEGUNDOS_VISIBLE = 3000


class PanelFramesSeleccionados(QWidget):
    """Overlay modal breve con los frames elegidos."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("overlay_frames")
        self.setAttribute(Qt.WA_StyledBackground, True)  # pinta el fondo translucido

        self._efecto = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._efecto)
        self._anim = QPropertyAnimation(self._efecto, b"opacity", self)

        raiz = QVBoxLayout(self)
        raiz.setAlignment(Qt.AlignCenter)

        self.tarjeta = QFrame()
        self.tarjeta.setObjectName("tarjeta_seleccion")
        capa = QVBoxLayout(self.tarjeta)
        capa.setContentsMargins(22, 18, 22, 20)
        capa.setSpacing(14)

        titulo = QLabel("Frames seleccionados")
        titulo.setObjectName("titulo_seleccion")
        titulo.setAlignment(Qt.AlignCenter)
        capa.addWidget(titulo)

        contenedor_fila = QWidget()
        self._fila = QHBoxLayout(contenedor_fila)
        self._fila.setSpacing(10)
        self._fila.setAlignment(Qt.AlignCenter)
        capa.addWidget(contenedor_fila)

        raiz.addWidget(self.tarjeta)
        self.hide()

        self._cerrar = QTimer(self)
        self._cerrar.setSingleShot(True)
        self._cerrar.timeout.connect(self._desvanecer)

    def mostrar(self, pixmaps: list) -> None:
        if not pixmaps:
            return
        while self._fila.count():
            item = self._fila.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for pixmap in pixmaps:
            etiqueta = QLabel()
            etiqueta.setObjectName("frame_seleccion")
            etiqueta.setFixedSize(190, 142)
            etiqueta.setScaledContents(True)
            etiqueta.setPixmap(pixmap)
            self._fila.addWidget(etiqueta)

        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()

        self._anim.stop()
        self._anim.setDuration(220)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._cerrar.start(_SEGUNDOS_VISIBLE)

    def _desvanecer(self) -> None:
        self._anim.stop()
        self._anim.setDuration(320)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()
        # Garantiza ocultar tras el fundido (no depende del signal 'finished').
        QTimer.singleShot(380, self.hide)
