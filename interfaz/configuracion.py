import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfiguracionInterfaz:
    url_motor: str = os.getenv("URL_MOTOR", "http://127.0.0.1:8765")
    indice_camara: int = int(os.getenv("INDICE_CAMARA", "0"))
    intervalo_envio_ms: int = int(os.getenv("INTERVALO_ENVIO_MS", "500"))
