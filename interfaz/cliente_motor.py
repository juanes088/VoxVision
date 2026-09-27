import requests


class ClienteMotor:
    def __init__(self, url_motor: str):
        self.url_motor = url_motor.rstrip("/")
        self.sesion = requests.Session()

    def estado(self) -> dict:
        respuesta = self.sesion.get(f"{self.url_motor}/estado", timeout=3)
        respuesta.raise_for_status()
        return respuesta.json()

    # Nuevas funciones para sistema conversacional

    def actualizar_frame_contexto(self, jpeg: bytes) -> dict:
        """Actualiza el frame de contexto visual para conversación."""
        respuesta = self.sesion.post(
            f"{self.url_motor}/voz/actualizar-frame",
            files={"frame": ("frame.jpg", jpeg, "image/jpeg")},
            timeout=5,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def actualizar_frames_contexto(self, lista_jpeg: list[bytes]) -> dict:
        """Envia varios keyframes (hasta 3) para la proxima consulta."""
        archivos = [
            ("frames", (f"frame_{i}.jpg", jpeg, "image/jpeg"))
            for i, jpeg in enumerate(lista_jpeg)
        ]
        respuesta = self.sesion.post(
            f"{self.url_motor}/voz/actualizar-frames",
            files=archivos,
            timeout=10,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def establecer_proveedor(self, modo: str) -> dict:
        """Cambia el proveedor de vision del motor (claude / local)."""
        respuesta = self.sesion.post(
            f"{self.url_motor}/voz/proveedor",
            data={"modo": modo},
            timeout=10,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def iniciar_escucha(self) -> dict:
        """Inicia la captura de audio del micrófono."""
        respuesta = self.sesion.post(
            f"{self.url_motor}/voz/iniciar-escucha",
            timeout=5,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def detener_y_procesar(self) -> dict:
        """Detiene la captura y procesa la conversación completa."""
        respuesta = self.sesion.post(
            f"{self.url_motor}/voz/detener-y-procesar",
            timeout=300,  # Primera carga de modelos y respuesta multimodal
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def conversar_texto(self, texto: str, incluir_vision: bool = True) -> dict:
        """Envía texto directamente para conversación."""
        respuesta = self.sesion.post(
            f"{self.url_motor}/voz/conversar",
            data={"texto": texto, "incluir_vision": str(incluir_vision).lower()},
            timeout=300,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def limpiar_historial(self) -> dict:
        """Limpia el historial de conversación."""
        respuesta = self.sesion.post(
            f"{self.url_motor}/voz/limpiar-historial",
            timeout=5,
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def obtener_estado(self) -> dict:
        """Obtiene el estado del sistema (alias de estado())."""
        return self.estado()

    def obtener_estado_voz(self) -> dict:
        """Obtiene el estado del sistema de voz, incluida la memoria visual."""
        respuesta = self.sesion.get(f"{self.url_motor}/voz/estado", timeout=3)
        respuesta.raise_for_status()
        return respuesta.json()
