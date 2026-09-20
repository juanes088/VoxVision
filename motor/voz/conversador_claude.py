import base64
import io
import logging
from typing import Any

from openai import OpenAI
from PIL import Image

from motor.configuracion import Configuracion

registro = logging.getLogger(__name__)

PROMPT_SISTEMA = (
    "Eres un asistente de voz con visión: ves al usuario EN VIVO a través de su "
    "cámara. Responde en español, breve y natural, sobre lo que ves y lo que te "
    "dice. Cuando comentes lo que ves, habla como si lo vieras por la cámara "
    "(por ejemplo: 'te veo por la cámara...'); NUNCA digas 'en la foto', 'en la "
    "imagen' ni 'en los fotogramas'. Básate solo en lo que realmente se ve; si "
    "un detalle no se distingue con claridad (por ejemplo la marca o el modelo "
    "de un objeto), dilo con honestidad en vez de adivinar, y no cambies tu "
    "respuesta solo para complacer al usuario."
)


class ConversadorClaude:
    """
    Conversador multimodal por API de Claude (vía aiapiflow, OpenAI-compatible).

    Misma interfaz que ConversadorQwen para intercambiarlos. Solo la visión
    y la redacción salen a la API; Whisper y Piper siguen locales.
    """

    def __init__(self, configuracion: Configuracion):
        if not configuracion.clave_api_ia:
            raise RuntimeError("Falta CLAVE_API_IA en .env")
        self.configuracion = configuracion
        self.modelo = configuracion.modelo_ia
        self.cliente = OpenAI(
            api_key=configuracion.clave_api_ia,
            base_url=configuracion.url_base_ia,
            timeout=configuracion.tiempo_espera_ia,
        )
        self._historial_conversacion: list[dict[str, Any]] = []
        self.max_turnos_historial = configuracion.turnos_chat_maximos

    def conversar(
        self,
        texto_usuario: str,
        imagen: Image.Image | None = None,
        contexto_reciente: str = "",
        imagenes_pasado: list[Image.Image] | None = None,
        resetear_historial: bool = False,
    ) -> str:
        if resetear_historial:
            self._historial_conversacion = []

        imagenes_pasado = imagenes_pasado or []

        contenido_usuario: list[dict[str, Any]] = [
            {"type": "text", "text": texto_usuario}
        ]
        for keyframe in imagenes_pasado:
            contenido_usuario.append(self._parte_imagen(keyframe))
        if imagen is not None:
            contenido_usuario.append(self._parte_imagen(imagen))

        mensajes: list[dict[str, Any]] = [
            {"role": "system", "content": PROMPT_SISTEMA}
        ]
        for turno in self._historial_conversacion[-self.max_turnos_historial:]:
            mensajes.append({"role": turno["role"], "content": turno["text"]})
        mensajes.append({"role": "user", "content": contenido_usuario})

        respuesta = self._pedir(mensajes)

        self._historial_conversacion.append({"role": "user", "text": texto_usuario})
        self._historial_conversacion.append({"role": "assistant", "text": respuesta})
        registro.info(
            "Claude: usuario='%s' asistente='%s'",
            texto_usuario[:50],
            respuesta[:50],
        )
        return respuesta

    def describir_escena(self, imagen: Image.Image) -> str:
        """No usado (captor apagado); stub por compatibilidad."""
        return ""

    def limpiar_historial(self) -> None:
        self._historial_conversacion = []
        registro.info("Historial de conversación limpiado (Claude)")

    def _pedir(self, mensajes: list[dict[str, Any]]) -> str:
        try:
            respuesta = self.cliente.chat.completions.create(
                model=self.modelo,
                temperature=0,
                max_tokens=self.configuracion.qwen_max_nuevos_tokens,
                messages=mensajes,
            )
            return (respuesta.choices[0].message.content or "").strip()
        except Exception:  # noqa: BLE001
            registro.exception("Error llamando a Claude")
            return "No pude procesar la imagen en este momento. Intenta de nuevo."

    @staticmethod
    def _parte_imagen(imagen: Image.Image) -> dict[str, Any]:
        flujo = io.BytesIO()
        imagen.convert("RGB").save(flujo, format="JPEG", quality=90)
        codificada = base64.b64encode(flujo.getvalue()).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{codificada}"},
        }
