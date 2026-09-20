import logging
import time
from threading import Event, Lock, Thread
from typing import Callable

import numpy as np
from PIL import Image

from motor.percepcion.buffer_visual import BufferVisual

registro = logging.getLogger(__name__)

# Tamano al que se reduce el frame antes de comparar y describir. Mantiene los
# captions rapidos y acota la RAM del ring buffer de keyframes.
_LADO_TRABAJO = 512
# Rejilla para la deteccion de cambio de escena. Comparar 32x32 en gris es
# suficiente para saber si "paso algo" sin gastar GPU.
_REJILLA_DIFF = 32


class CaptadorPercepcion:
    """
    Percepcion continua (arquitectura A).

    Un hilo de fondo toma el ultimo frame recibido cada ~1/fps segundos. Si la
    escena cambio respecto al ultimo frame descrito, pide una descripcion corta
    al captioner (con prioridad de fondo, para no frenar la conversacion) y la
    anexa al buffer como texto. Asi, cuando el usuario habla, el pasado ya es
    texto y no hay que reprocesar decenas de fotogramas.
    """

    def __init__(
        self,
        buffer: BufferVisual,
        describir_escena: Callable[[Image.Image], str] | None = None,
        fps: float = 1.0,
        umbral_cambio: float = 0.06,
    ):
        self.buffer = buffer
        # Si es None, el captor solo guarda escenas (modo "B sola", sin captions
        # de texto ni gasto de GPU en descripciones).
        self.describir_escena = describir_escena
        self.intervalo = 1.0 / fps if fps > 0 else 1.0
        self.umbral_cambio = umbral_cambio

        self._lock = Lock()
        self._frame_pendiente: Image.Image | None = None
        self._huella_previa: np.ndarray | None = None
        self._detener = Event()
        self._hilo: Thread | None = None

    def actualizar_frame(self, imagen: Image.Image) -> None:
        """Registra el ultimo frame recibido. No bloquea: solo guarda el slot."""
        with self._lock:
            self._frame_pendiente = imagen

    def iniciar(self) -> None:
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._detener.clear()
        self._hilo = Thread(target=self._bucle, name="captador-percepcion", daemon=True)
        self._hilo.start()
        registro.info("Captador de percepcion iniciado (intervalo=%.2fs)", self.intervalo)

    def detener(self) -> None:
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join(timeout=self.intervalo * 2)
            self._hilo = None
        registro.info("Captador de percepcion detenido")

    def _bucle(self) -> None:
        while not self._detener.wait(self.intervalo):
            try:
                self._procesar_tick()
            except Exception:  # noqa: BLE001 - el hilo nunca debe morir
                registro.exception("Error en el ciclo de percepcion; se continua")

    def _procesar_tick(self) -> None:
        with self._lock:
            frame = self._frame_pendiente
        if frame is None:
            return

        reducido = self._reducir(frame)
        huella = self._huella(reducido)

        if not self._escena_cambio(huella):
            return

        self._huella_previa = huella
        self.buffer.agregar_frame(reducido)

        # Captions de texto solo si hay describir_escena (modo "C"). En "B sola"
        # no se llama al VLM: el captor es puro guardado de escenas.
        if self.describir_escena is not None:
            texto = self.describir_escena(reducido)
            if texto:
                self.buffer.agregar_observacion(texto)
                registro.debug("Observacion de escena: %s", texto)

    def _escena_cambio(self, huella: np.ndarray) -> bool:
        if self._huella_previa is None:
            return True
        diferencia = float(np.mean(np.abs(huella - self._huella_previa)))
        return diferencia >= self.umbral_cambio

    @staticmethod
    def _reducir(imagen: Image.Image) -> Image.Image:
        imagen = imagen.convert("RGB")
        lado = max(imagen.size)
        if lado <= _LADO_TRABAJO:
            return imagen
        escala = _LADO_TRABAJO / lado
        nuevo = (round(imagen.width * escala), round(imagen.height * escala))
        return imagen.resize(nuevo, Image.BILINEAR)

    @staticmethod
    def _huella(imagen: Image.Image) -> np.ndarray:
        """Vector normalizado 0-1 de una miniatura en gris para medir cambios."""
        gris = imagen.convert("L").resize((_REJILLA_DIFF, _REJILLA_DIFF), Image.BILINEAR)
        return np.asarray(gris, dtype=np.float32) / 255.0
