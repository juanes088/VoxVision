import logging
from pathlib import Path
from threading import Lock

import numpy as np
import torch
import whisper

from motor.configuracion import Configuracion
from motor.vision.gestor_inferencia import GestorInferencia

registro = logging.getLogger(__name__)


class TranscriptorWhisper:
    """Transcriptor de audio a texto usando Whisper."""

    def __init__(self, configuracion: Configuracion, gestor: GestorInferencia):
        self.configuracion = configuracion
        self.gestor = gestor
        self._modelo = None
        self._dispositivo = None
        self._bloqueo_carga = Lock()

    def transcribir(self, audio: np.ndarray, idioma: str = "es") -> str:
        """
        Transcribe audio a texto.
        
        Args:
            audio: Array numpy con audio (16kHz, mono, float32)
            idioma: Código de idioma (default: español)
            
        Returns:
            Texto transcrito
        """
        if len(audio) == 0:
            return ""
        
        with self.gestor.reservar_gpu():
            self._asegurar_modelo()
            
            # Whisper espera audio normalizado entre -1 y 1
            if audio.dtype == np.int16:
                audio = audio.astype(np.float32) / 32768.0
            elif audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            
            resultado = self._modelo.transcribe(
                audio,
                language=idioma,
                fp16=self._dispositivo is not None and self._dispositivo.startswith("cuda"),
                verbose=False,
            )
            
            texto = resultado["text"].strip()
            registro.info("Transcripción completada: %d caracteres", len(texto))
            return texto

    def transcribir_desde_archivo(self, ruta: Path, idioma: str = "es") -> str:
        """Transcribe audio desde un archivo."""
        with self.gestor.reservar_gpu():
            self._asegurar_modelo()
            
            resultado = self._modelo.transcribe(
                str(ruta),
                language=idioma,
                fp16=self._dispositivo is not None and self._dispositivo.startswith("cuda"),
                verbose=False,
            )
            
            texto = resultado["text"].strip()
            registro.info("Transcripción desde archivo %s: %d caracteres", ruta.name, len(texto))
            return texto

    def _asegurar_modelo(self) -> None:
        """Carga el modelo Whisper si no está cargado."""
        if self._modelo is not None:
            return
        
        with self._bloqueo_carga:
            if self._modelo is not None:
                return
            
            modelo_nombre = self.configuracion.modelo_whisper
            dispositivo = self._resolver_dispositivo()

            registro.info(
                "Cargando Whisper: modelo=%s dispositivo=%s",
                modelo_nombre,
                dispositivo,
            )
            self._modelo = whisper.load_model(modelo_nombre, device=dispositivo)
            self._dispositivo = dispositivo
            registro.info("Whisper cargado exitosamente en %s", dispositivo)

    def _resolver_dispositivo(self) -> str:
        """Valida CUDA con una operación real antes de cargar Whisper."""
        solicitado = self.configuracion.dispositivo
        if not solicitado.startswith("cuda"):
            return "cpu"
        if not torch.cuda.is_available():
            registro.warning("CUDA no está disponible; Whisper usará CPU")
            return "cpu"

        try:
            prueba = torch.zeros(1, device=solicitado)
            prueba.add_(1)
            torch.cuda.synchronize()
        except RuntimeError as error:
            registro.warning("CUDA no pudo ejecutar Whisper (%s); se usará CPU", error)
            return "cpu"
        return solicitado
