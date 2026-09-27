"""
Seleccion de keyframes por clustering (enfoque VSUMM) y utilidades.

En vez de comparar frames consecutivos (que se deja dominar por el movimiento
de la cara), se agrupan los frames por su HISTOGRAMA DE COLOR con k-means y se
elige el mejor frame de cada grupo. Asi se obtienen los estados visuales
DISTINTOS del clip (cara, celular en mano, audifonos, etc.), aunque el objeto
aparezca en pocos fotogramas. Todo con cv2+numpy, en CPU y en milisegundos.

Referencia: VSUMM (histogramas de color + k-means) y variantes.
"""
import cv2
import numpy as np


def nitidez(frame_rgb: np.ndarray) -> float:
    """Nitidez por varianza del Laplaciano (mayor = mas nitido)."""
    gris = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gris, cv2.CV_64F).var())


def elegir_mas_nitido(frames_rgb: list[np.ndarray]) -> np.ndarray | None:
    if not frames_rgb:
        return None
    return max(frames_rgb, key=nitidez)


def _histograma(frame_rgb: np.ndarray) -> np.ndarray:
    """
    Firma de color del frame: histograma HSV (8 tonos x 4 sat x 4 valor).
    Robusto a pequenos movimientos y sensible a "aparece un objeto oscuro/nuevo".
    """
    hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten().astype(np.float32)


def seleccionar_keyframes(
    frames_rgb: list[np.ndarray],
    maximo: int = 5,
    umbral_cambio: float = 0.06,  # compatibilidad; no usado en clustering
) -> list[int]:
    """
    Devuelve los indices de hasta `maximo` keyframes representativos.

    1. Firma de color (histograma HSV) de cada frame.
    2. k-means: agrupa los frames en `maximo` grupos por similitud de color.
    3. De cada grupo toma el frame mas nitido.
    4. Devuelve los indices en orden temporal.
    """
    n = len(frames_rgb)
    if n == 0:
        return []
    if n <= maximo:
        return list(range(n))

    caracteristicas = np.array([_histograma(f) for f in frames_rgb], dtype=np.float32)
    k = min(maximo, n)
    criterios = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, etiquetas, _ = cv2.kmeans(
        caracteristicas, k, None, criterios, 5, cv2.KMEANS_PP_CENTERS
    )
    etiquetas = etiquetas.flatten()

    elegidos: list[int] = []
    for grupo in range(k):
        indices = [i for i in range(n) if etiquetas[i] == grupo]
        if not indices:
            continue
        mejor = max(indices, key=lambda i: nitidez(frames_rgb[i]))
        elegidos.append(mejor)
    return sorted(elegidos)


def crear_montaje(
    frames_rgb: list[np.ndarray],
    columnas: int = 2,
    lado_celda: int = 384,
) -> np.ndarray | None:
    """Compone frames en cuadricula RGB (queda por si se quiere previsualizar)."""
    if not frames_rgb:
        return None
    if len(frames_rgb) == 1:
        return frames_rgb[0]

    import math

    filas = math.ceil(len(frames_rgb) / columnas)
    lienzo = np.full((filas * lado_celda, columnas * lado_celda, 3), 20, dtype=np.uint8)
    for indice, frame in enumerate(frames_rgb):
        alto0, ancho0 = frame.shape[:2]
        escala = min(lado_celda / ancho0, lado_celda / alto0)
        celda = cv2.resize(
            frame, (max(1, int(ancho0 * escala)), max(1, int(alto0 * escala))),
            interpolation=cv2.INTER_AREA,
        )
        alto, ancho = celda.shape[:2]
        fila, columna = divmod(indice, columnas)
        y = fila * lado_celda + (lado_celda - alto) // 2
        x = columna * lado_celda + (lado_celda - ancho) // 2
        lienzo[y:y + alto, x:x + ancho] = celda
    return lienzo
