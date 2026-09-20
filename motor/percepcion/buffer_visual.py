import logging
import math
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock

from PIL import Image

registro = logging.getLogger(__name__)


@dataclass
class Observacion:
    """Una descripcion textual de la escena en un instante."""

    momento: float
    texto: str


@dataclass
class FrameConMarca:
    """Un fotograma crudo guardado en RAM para escalado a keyframes."""

    momento: float
    imagen: Image.Image


class BufferVisual:
    """
    Memoria visual de corto plazo, 100% en RAM.

    Guarda dos cosas de la ultima ventana de tiempo:
    - Observaciones de texto (via A): lo que el captioner de fondo ya resumio.
      Es la fuente rapida de contexto: al responder solo se lee texto.
    - Fotogramas crudos (via B): un ring buffer acotado para poder adjuntar
      uno o dos keyframes cuando la pregunta es sobre el pasado.

    Es seguro entre hilos: el captioner de fondo escribe mientras la
    conversacion lee.
    """

    def __init__(
        self,
        ventana_segundos: float = 60.0,
        max_frames: int = 90,
    ):
        self.ventana_segundos = ventana_segundos
        self._lock = Lock()
        self._observaciones: deque[Observacion] = deque()
        self._frames: deque[FrameConMarca] = deque(maxlen=max_frames)

    def agregar_observacion(self, texto: str, momento: float | None = None) -> None:
        """
        Anexa una descripcion de escena. Colapsa duplicados consecutivos:
        si el texto repite el de la ultima observacion, solo refresca su marca
        de tiempo en vez de acumular ruido ("sigue tomando cafe").
        """
        texto = texto.strip()
        if not texto:
            return

        ahora = momento if momento is not None else time.monotonic()
        with self._lock:
            self._purgar(ahora)
            if self._observaciones and self._observaciones[-1].texto.lower() == texto.lower():
                self._observaciones[-1].momento = ahora
                return
            self._observaciones.append(Observacion(momento=ahora, texto=texto))

    def agregar_frame(self, imagen: Image.Image, momento: float | None = None) -> None:
        """Guarda un fotograma crudo en el ring buffer (para keyframes)."""
        ahora = momento if momento is not None else time.monotonic()
        with self._lock:
            self._frames.append(FrameConMarca(momento=ahora, imagen=imagen))

    def resumen_texto(self, ventana_segundos: float | None = None) -> str:
        """
        Devuelve las observaciones de la ventana como texto listo para el
        prompt, ordenadas de mas antigua a mas reciente:

            hace 32s: el usuario abre el portatil
            hace 8s: el usuario toma cafe

        Cadena vacia si no hay nada reciente.
        """
        ventana = ventana_segundos if ventana_segundos is not None else self.ventana_segundos
        ahora = time.monotonic()
        with self._lock:
            self._purgar(ahora)
            lineas = [
                f"hace {int(ahora - obs.momento)}s: {obs.texto}"
                for obs in self._observaciones
                if ahora - obs.momento <= ventana
            ]
        return "\n".join(lineas)

    def keyframes(self, cantidad: int = 2) -> list[Image.Image]:
        """
        Devuelve hasta `cantidad` fotogramas recientes distribuidos en la
        ventana (el mas viejo y el mas nuevo primero), para adjuntarlos cuando
        se pregunta por el pasado. Lista vacia si no hay frames.
        """
        if cantidad <= 0:
            return []
        with self._lock:
            frames = list(self._frames)
        if not frames:
            return []
        if len(frames) <= cantidad:
            return [f.imagen for f in frames]

        # Muestreo uniforme para cubrir la ventana sin repetir fotogramas casi
        # identicos consecutivos.
        paso = (len(frames) - 1) / (cantidad - 1) if cantidad > 1 else 0
        indices = sorted({round(i * paso) for i in range(cantidad)})
        return [frames[i].imagen for i in indices]

    def montaje_pasado(
        self,
        cantidad: int = 4,
        columnas: int = 2,
        lado_celda: int = 384,
    ) -> Image.Image | None:
        """
        Arma un montaje (tira de fotos) con las escenas distintas del ultimo
        minuto, en UNA sola imagen. Las celdas van en orden temporal: arriba-
        izquierda la mas antigua, abajo-derecha la mas reciente.

        Devuelve None si aun no hay escenas guardadas.
        """
        imagenes = self.keyframes(cantidad)
        if not imagenes:
            return None

        filas = math.ceil(len(imagenes) / columnas)
        lienzo = Image.new(
            "RGB", (columnas * lado_celda, filas * lado_celda), (20, 20, 20)
        )
        for indice, imagen in enumerate(imagenes):
            celda = imagen.convert("RGB").copy()
            celda.thumbnail((lado_celda, lado_celda), Image.BILINEAR)
            fila, columna = divmod(indice, columnas)
            desplazamiento_x = columna * lado_celda + (lado_celda - celda.width) // 2
            desplazamiento_y = fila * lado_celda + (lado_celda - celda.height) // 2
            lienzo.paste(celda, (desplazamiento_x, desplazamiento_y))
        return lienzo

    def ultimo_frame(self) -> Image.Image | None:
        with self._lock:
            return self._frames[-1].imagen if self._frames else None

    def limpiar(self) -> None:
        with self._lock:
            self._observaciones.clear()
            self._frames.clear()
        registro.info("Buffer visual limpiado")

    def estado(self) -> dict[str, int]:
        with self._lock:
            return {
                "observaciones": len(self._observaciones),
                "frames": len(self._frames),
            }

    def _purgar(self, ahora: float) -> None:
        """Elimina observaciones fuera de la ventana. Requiere el lock tomado."""
        limite = ahora - self.ventana_segundos
        while self._observaciones and self._observaciones[0].momento < limite:
            self._observaciones.popleft()
