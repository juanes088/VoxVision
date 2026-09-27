import logging
import queue
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

registro = logging.getLogger(__name__)


class CapturadorAudio:
    """Captura audio del micrófono en chunks para procesamiento streaming."""

    def __init__(
        self,
        frecuencia_muestreo: int = 16000,
        canales: int = 1,
        duracion_chunk_segundos: float = 0.5,
    ):
        self.frecuencia_muestreo = frecuencia_muestreo
        self.canales = canales
        self.duracion_chunk_segundos = duracion_chunk_segundos
        self.tamano_chunk = int(frecuencia_muestreo * duracion_chunk_segundos)
        
        self._cola_audio: queue.Queue = queue.Queue()
        self._stream = None
        self._grabando = False
        self._lock = threading.Lock()

    def iniciar_grabacion(self) -> None:
        """Inicia la captura de audio."""
        with self._lock:
            if self._grabando:
                return
            
            self._grabando = True
            self._cola_audio = queue.Queue()
            
            def callback(indata, frames, time, status):
                if status:
                    registro.warning(f"Estado del stream de audio: {status}")
                if self._grabando:
                    self._cola_audio.put(indata.copy())
            
            self._stream = sd.InputStream(
                samplerate=self.frecuencia_muestreo,
                channels=self.canales,
                callback=callback,
                blocksize=self.tamano_chunk,
            )
            self._stream.start()
            registro.info("Captura de audio iniciada: %dHz, %d canal(es)", 
                         self.frecuencia_muestreo, self.canales)

    def detener_grabacion(self) -> np.ndarray:
        """Detiene la captura y retorna todo el audio grabado."""
        with self._lock:
            if not self._grabando:
                return np.array([])
            
            self._grabando = False
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        
        # Recolectar todos los chunks
        chunks = []
        while not self._cola_audio.empty():
            try:
                chunks.append(self._cola_audio.get_nowait())
            except queue.Empty:
                break
        
        if not chunks:
            return np.array([])
        
        audio_completo = np.concatenate(chunks, axis=0)
        # Convertir a mono si es necesario y aplanar
        if audio_completo.ndim > 1:
            audio_completo = audio_completo.mean(axis=1)
        
        registro.info("Audio capturado: %.2f segundos", 
                     len(audio_completo) / self.frecuencia_muestreo)
        return audio_completo

    def guardar_audio(self, audio: np.ndarray, ruta: Path) -> None:
        """Guarda el audio en un archivo WAV."""
        ruta.parent.mkdir(parents=True, exist_ok=True)
        sf.write(ruta, audio, self.frecuencia_muestreo)
        registro.info("Audio guardado en: %s", ruta)

    def esta_grabando(self) -> bool:
        """Verifica si está grabando actualmente."""
        return self._grabando

    def limpiar(self) -> None:
        """Limpia recursos."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
