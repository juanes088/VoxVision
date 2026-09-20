from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host_motor: str = "127.0.0.1"
    puerto_motor: int = 8765

    # Proveedor de vision+conversacion (conmutable en caliente desde la interfaz):
    #   "claude" -> API (aiapiflow, mejor calidad)
    #   "local"  -> Qwen2.5-VL 3B en la GPU
    # Whisper (STT) y Piper (TTS) siempre son locales.
    proveedor_vision: str = "claude"

    # Claude via aiapiflow (OpenAI-compatible)
    url_base_ia: str = "https://aiapiflow.com/v1"
    clave_api_ia: str = ""
    modelo_ia: str = "claude-sonnet-5"
    tiempo_espera_ia: float = 45.0

    # Modelos locales
    dispositivo: str = "cuda"
    modelo_qwen_vl: str = "Qwen/Qwen2.5-VL-3B-Instruct"
    modelo_whisper: str = "small"
    token_huggingface: str = ""
    cuantizacion_4bit: bool = True

    # Limites de Qwen-VL local en tokens visuales (parches de 28x28).
    qwen_min_pixels: int = 200704
    qwen_max_pixels: int = 1003520
    qwen_max_nuevos_tokens: int = 128
    qwen_max_tokens_descripcion: int = 40

    # Piper TTS
    ruta_modelo_piper: Path = Path("modelos/piper/es_ES-davefx-medium.onnx")
    ruta_ejecutable_piper: str = "piper"

    turnos_chat_maximos: int = 8

    # Percepcion de fondo (memoria visual): desactivada. La seleccion de frames
    # la hace la interfaz; el motor solo recibe la imagen final. Se conserva la
    # bandera por si se quiere reactivar.
    percepcion_activa: bool = False
    percepcion_fps: float = 1.0
    percepcion_ventana_segundos: float = 60.0
    percepcion_umbral_cambio: float = 0.06
    percepcion_max_frames: int = 90
    percepcion_keyframes_pasado: int = 4
    percepcion_montaje_columnas: int = 2
    percepcion_montaje_lado_celda: int = 384
    percepcion_captions_texto: bool = False


@lru_cache(maxsize=1)
def obtener_configuracion() -> Configuracion:
    return Configuracion()
