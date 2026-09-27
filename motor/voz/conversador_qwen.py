import logging
from typing import Any

import torch
from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import (
    AutoConfig,
    AutoProcessor,
    BitsAndBytesConfig,
    Qwen2VLForConditionalGeneration,
    Qwen2_5_VLForConditionalGeneration,
)

from motor.configuracion import Configuracion
from motor.vision.gestor_inferencia import GestorInferencia

registro = logging.getLogger(__name__)

PROMPT_SISTEMA = (
    "Eres un asistente de voz con visión: ves al usuario EN VIVO a través de su "
    "cámara. Responde en español, breve y natural, sobre lo que ves y lo que te "
    "dice. Cuando comentes lo que ves, habla como si lo vieras por la cámara "
    "('te veo por la cámara...'); nunca digas 'en la foto' ni 'en la imagen'."
)

# Prompt para el captioner de fondo: una sola frase, sin adornos, para que la
# observacion sea barata de generar y facil de reutilizar como contexto.
PROMPT_DESCRIPCION_ESCENA = (
    "Describe en una sola frase corta y objetiva que hace la persona y los "
    "objetos relevantes que se ven. Sin saludos ni opiniones."
)


class ConversadorQwen:
    """Conversador multimodal usando Qwen2.5-VL con cuantización int4."""

    def __init__(self, configuracion: Configuracion, gestor: GestorInferencia):
        self.configuracion = configuracion
        self.gestor = gestor
        self._procesador = None
        self._modelo = None
        self._dispositivo = None
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
        """
        Mantiene una conversación con contexto visual.

        Args:
            texto_usuario: Lo que dijo el usuario
            imagen: Imagen actual de la cámara (opcional)
            contexto_reciente: Resumen en texto de lo visto en el último minuto
                (vía rápida: el pasado ya viene resumido, no se reprocesa)
            imagenes_pasado: Keyframes opcionales del pasado (escalón lento, solo
                cuando la pregunta lo amerita)
            resetear_historial: Si True, limpia el historial de conversación

        Returns:
            Respuesta del asistente
        """
        if resetear_historial:
            self._historial_conversacion = []

        imagenes_pasado = imagenes_pasado or []

        with self.gestor.reservar_gpu(), torch.inference_mode():
            self._asegurar_modelo()

            # Contenido del usuario en forma CANONICA de Qwen-VL: las imagenes
            # van DENTRO del contenido, para que process_vision_info las procese
            # y redimensione correctamente. Orden: keyframes -> frame actual.
            contenido_usuario: list[dict[str, Any]] = []
            for keyframe in imagenes_pasado:
                contenido_usuario.append({"type": "image", "image": keyframe})
            if imagen is not None:
                contenido_usuario.append({"type": "image", "image": imagen})
            contenido_usuario.append({"type": "text", "text": texto_usuario})

            # Mensajes: system corto + historial (solo texto) + turno actual.
            mensajes = [
                {"role": "system", "content": [{"type": "text", "text": PROMPT_SISTEMA}]}
            ]
            for turno in self._historial_conversacion[-self.max_turnos_historial:]:
                mensajes.append({
                    "role": turno["role"],
                    "content": [{"type": "text", "text": turno["text"]}],
                })
            mensajes.append({"role": "user", "content": contenido_usuario})

            respuesta = self._generar(mensajes)

            # Red anti-refusal: si hay imagen y el modelo se niega a ver, se
            # regenera sembrando el inicio de la respuesta. Qwen ignora las
            # reglas del system prompt, pero no puede contradecir lo ya escrito.
            hay_imagen = imagen is not None or bool(imagenes_pasado)
            if hay_imagen and self._parece_refusal(respuesta):
                registro.info("Refusal detectado; regenerando con semilla")
                respuesta = self._generar(mensajes, semilla="En la imagen veo")

            # Actualizar historial
            self._historial_conversacion.append({
                "role": "user",
                "text": texto_usuario,
            })
            self._historial_conversacion.append({
                "role": "assistant",
                "text": respuesta,
            })
            
            registro.info(
                "Conversación: usuario='%s' asistente='%s' (turnos=%d)",
                texto_usuario[:50],
                respuesta[:50],
                len(self._historial_conversacion) // 2,
            )
            
            return respuesta

    def _generar(self, mensajes: list[dict[str, Any]], semilla: str = "") -> str:
        """
        Ejecuta una generacion greedy en forma canonica (process_vision_info).

        Si `semilla` no es vacia, se antepone al inicio de la respuesta del
        asistente: el modelo continua desde ahi y no puede empezar con un
        refusal ("Lo siento, no puedo ver...").
        """
        texto_prompt = self._procesador.apply_chat_template(
            mensajes, tokenize=False, add_generation_prompt=True
        )
        if semilla:
            texto_prompt = texto_prompt + semilla

        imagenes, videos = process_vision_info(mensajes)
        entradas = self._procesador(
            text=[texto_prompt],
            images=imagenes,
            videos=videos,
            padding=True,
            return_tensors="pt",
        ).to(self._modelo.device)

        ids_generados = self._modelo.generate(
            **entradas,
            max_new_tokens=self.configuracion.qwen_max_nuevos_tokens,
            do_sample=False,
        )
        ids_recortados = [
            salida[len(entrada):]
            for entrada, salida in zip(entradas.input_ids, ids_generados)
        ]
        salida = self._procesador.batch_decode(
            ids_recortados,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        return f"{semilla} {salida}".strip() if semilla else salida

    @staticmethod
    def _parece_refusal(texto: str) -> bool:
        """Detecta el refusal tipico de 'no puedo ver imagenes'."""
        minuscula = texto.lower()
        senales = (
            "no puedo ver",
            "no tengo la capacidad",
            "no tengo capacidad",
            "como asistente de voz",
            "no puedo acceder",
            "no veo nada",
            "no tengo acceso",
            "no puedo procesar imag",
            "describir cómo te ven",
            "describir como te ven",
            "pero como asistente",
        )
        return any(senal in minuscula for senal in senales)

    def describir_escena(self, imagen: Image.Image) -> str:
        """
        Genera una descripción de una sola frase para el captioner de fondo.

        Corre con prioridad de fondo: si hay una conversación esperando la GPU,
        cede el turno. No toca el historial ni sintetiza voz.
        """
        with self.gestor.prioridad_fondo(), self.gestor.reservar_gpu(), torch.inference_mode():
            self._asegurar_modelo()

            mensajes = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": PROMPT_DESCRIPCION_ESCENA},
                    ],
                }
            ]
            texto_prompt = self._procesador.apply_chat_template(
                mensajes, tokenize=False, add_generation_prompt=True
            )
            entradas = self._procesador(
                text=[texto_prompt],
                images=[imagen],
                padding=True,
                return_tensors="pt",
            ).to(self._modelo.device)

            # Determinista y con pocos tokens: la observación debe ser barata.
            ids_generados = self._modelo.generate(
                **entradas,
                max_new_tokens=self.configuracion.qwen_max_tokens_descripcion,
                do_sample=False,
            )
            ids_recortados = [
                salida[len(entrada):]
                for entrada, salida in zip(entradas.input_ids, ids_generados)
            ]
            return self._procesador.batch_decode(
                ids_recortados,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0].strip()

    def limpiar_historial(self) -> None:
        """Limpia el historial de conversación."""
        self._historial_conversacion = []
        registro.info("Historial de conversación limpiado")

    def _asegurar_modelo(self) -> None:
        """Carga el modelo Qwen-VL con cuantización int4 si no está cargado."""
        if self._modelo is not None:
            return
        
        argumentos = {}
        if self.configuracion.token_huggingface:
            argumentos["token"] = self.configuracion.token_huggingface
        
        # Detectar arquitectura del modelo
        configuracion_modelo = AutoConfig.from_pretrained(
            self.configuracion.modelo_qwen_vl, **argumentos
        )
        clase_modelo = self._clase_modelo(configuracion_modelo.model_type)
        
        dispositivo = self._resolver_dispositivo()

        # Configuración de cuantización int4
        config_cuantizacion = None
        if self.configuracion.cuantizacion_4bit and dispositivo.startswith("cuda"):
            config_cuantizacion = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            registro.info("Cuantización int4 activada")
        
        # Cargar procesador
        self._procesador = AutoProcessor.from_pretrained(
            self.configuracion.modelo_qwen_vl,
            min_pixels=self.configuracion.qwen_min_pixels,
            max_pixels=self.configuracion.qwen_max_pixels,
            **argumentos,
        )
        
        # Cargar modelo
        argumentos_modelo = {**argumentos}

        if config_cuantizacion is not None:
            argumentos_modelo["device_map"] = "auto"
            argumentos_modelo["quantization_config"] = config_cuantizacion
        else:
            argumentos_modelo["torch_dtype"] = "auto" if dispositivo.startswith("cuda") else torch.float32
            argumentos_modelo["device_map"] = "auto" if dispositivo.startswith("cuda") else "cpu"
        
        self._modelo = clase_modelo.from_pretrained(
            self.configuracion.modelo_qwen_vl,
            **argumentos_modelo,
        )
        self._modelo.eval()
        self._dispositivo = dispositivo
        
        registro.info(
            "Qwen-VL conversador cargado: modelo=%s arquitectura=%s cuantizado=%s",
            self.configuracion.modelo_qwen_vl,
            configuracion_modelo.model_type,
            config_cuantizacion is not None,
        )

    def _resolver_dispositivo(self) -> str:
        """Usa CUDA solo cuando el binario de PyTorch puede ejecutar kernels."""
        solicitado = self.configuracion.dispositivo
        if not solicitado.startswith("cuda"):
            return "cpu"
        if not torch.cuda.is_available():
            registro.warning("CUDA no está disponible; Qwen usará CPU")
            return "cpu"
        try:
            prueba = torch.zeros(1, device=solicitado)
            prueba.add_(1)
            torch.cuda.synchronize()
        except RuntimeError as error:
            registro.warning("CUDA no pudo ejecutar Qwen (%s); se usará CPU", error)
            return "cpu"
        return solicitado

    @staticmethod
    def _clase_modelo(tipo_modelo: str):
        """Retorna la clase del modelo según su tipo."""
        clases = {
            "qwen2_vl": Qwen2VLForConditionalGeneration,
            "qwen2_5_vl": Qwen2_5_VLForConditionalGeneration,
        }
        try:
            return clases[tipo_modelo]
        except KeyError as error:
            raise RuntimeError(
                f"El modelo Qwen-VL '{tipo_modelo}' no es compatible. "
                "Usa una arquitectura qwen2_vl o qwen2_5_vl."
            ) from error
