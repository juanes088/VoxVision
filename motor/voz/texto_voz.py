import re

# Limpia el texto para el TTS: quita simbolos de markdown que Piper leeria en
# voz alta ("asterisco", "slash") y los convierte en pausas o comas naturales.

_VINETAS = re.compile(r"(?m)^[ \t]*[-*•]\s+")
_ESPACIOS = re.compile(r"[ \t]+")
_ANTES_PUNTUACION = re.compile(r"\s+([.,;:!?])")
_PUNTOS = re.compile(r"\.{2,}")
# Emojis y pictogramas: Piper no los pronuncia y rompen la codificacion.
_EMOJIS = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U00002190-\U000021FF"
    "]+",
    flags=re.UNICODE,
)


def limpiar_para_voz(texto: str) -> str:
    """Devuelve el texto listo para sintetizar (sin markdown ni '/')."""
    t = texto

    # Quitar emojis/pictogramas.
    t = _EMOJIS.sub("", t)
    # Vinetas de lista al inicio de linea -> nada (antes de tocar los '*').
    t = _VINETAS.sub("", t)
    # Enfasis markdown: negrita/cursiva/codigo/encabezados/tachado.
    for simbolo in ("**", "__", "*", "`", "#", "_", "~"):
        t = t.replace(simbolo, "")
    # Barra -> coma (ej. "MIUI/HyperOS" -> "MIUI, HyperOS").
    t = t.replace("/", ", ")

    # Saltos de linea -> pausa hablada.
    t = t.replace("\r", "")
    t = re.sub(r"\n{2,}", ". ", t)
    t = t.replace("\n", ". ")

    # Limpieza de espacios y puntuacion redundante.
    t = _ESPACIOS.sub(" ", t)
    t = _ANTES_PUNTUACION.sub(r"\1", t)
    t = _PUNTOS.sub(".", t)
    return t.strip()
