import numpy as np
from PIL import Image

# Debajo de este brillo medio (0-255) se considera que la escena esta oscura y
# conviene realzarla antes de la inferencia.
_UMBRAL_OSCURA = 110.0
# Gamma minimo permitido: valores mas bajos aclaran mas pero aplanan el detalle.
_GAMMA_MINIMO = 0.45


def realzar_si_oscura(imagen: Image.Image) -> Image.Image:
    """
    Aclara la imagen con correccion gamma solo cuando esta oscura.

    En poca luz la webcam pierde detalle y el modelo cuenta/observa peor. Si el
    brillo medio esta por encima del umbral, se devuelve la imagen sin tocar.
    """
    rgb = imagen.convert("RGB")
    brillo = float(np.asarray(rgb.convert("L"), dtype=np.float32).mean())
    if brillo >= _UMBRAL_OSCURA:
        return rgb

    # Cuanto mas oscura, menor gamma (mas aclarado), con un piso de seguridad.
    gamma = max(_GAMMA_MINIMO, brillo / (_UMBRAL_OSCURA * 1.6))
    lut = [round((i / 255.0) ** gamma * 255.0) for i in range(256)]
    return rgb.point(lut * 3)
