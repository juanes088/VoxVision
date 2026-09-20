import logging
import subprocess
from pathlib import Path
from threading import Lock

registro = logging.getLogger(__name__)


class SintetizadorPiper:
    """Sintetizador de texto a voz usando Piper."""

    def __init__(self, ruta_modelo: Path, ruta_ejecutable: Path | None = None):
        """
        Inicializa el sintetizador Piper.
        
        Args:
            ruta_modelo: Ruta al archivo .onnx del modelo de voz
            ruta_ejecutable: Ruta al ejecutable de Piper (opcional, busca en PATH)
        """
        self.ruta_modelo = ruta_modelo
        self.ruta_ejecutable = ruta_ejecutable or "piper"
        self._lock = Lock()
        
        # Verificar que el modelo existe
        if not ruta_modelo.exists():
            raise FileNotFoundError(f"Modelo de Piper no encontrado: {ruta_modelo}")
        
        # Verificar archivo de configuración .json
        self.ruta_config = ruta_modelo.with_suffix(".onnx.json")
        if not self.ruta_config.exists():
            raise FileNotFoundError(f"Configuración de modelo no encontrada: {self.ruta_config}")

    def sintetizar(self, texto: str, ruta_salida: Path) -> None:
        """
        Sintetiza texto a audio y lo guarda en un archivo.
        
        Args:
            texto: Texto a sintetizar
            ruta_salida: Ruta donde guardar el archivo WAV
        """
        if not texto.strip():
            registro.warning("Texto vacío, no se sintetiza audio")
            return
        
        with self._lock:
            ruta_salida.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                # Ejecutar Piper: echo "texto" | piper --model modelo.onnx --output_file salida.wav
                proceso = subprocess.Popen(
                    [
                        str(self.ruta_ejecutable),
                        "--model", str(self.ruta_modelo),
                        "--output_file", str(ruta_salida),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )

                stdout, stderr = proceso.communicate(input=texto, timeout=30)
                
                if proceso.returncode != 0:
                    raise RuntimeError(f"Piper falló: {stderr}")
                
                registro.info("Audio sintetizado: %s (%d caracteres)", 
                             ruta_salida.name, len(texto))
                
            except subprocess.TimeoutExpired:
                proceso.kill()
                raise RuntimeError("Piper excedió el tiempo de espera")
            except FileNotFoundError:
                raise RuntimeError(
                    f"Ejecutable de Piper no encontrado: {self.ruta_ejecutable}. "
                    "Instala Piper o especifica la ruta al ejecutable."
                )

    def sintetizar_streaming(self, texto: str) -> bytes:
        """
        Sintetiza texto y retorna el audio como bytes (sin guardar archivo).
        
        Args:
            texto: Texto a sintetizar
            
        Returns:
            Audio en formato WAV como bytes
        """
        if not texto.strip():
            return b""
        
        with self._lock:
            try:
                proceso = subprocess.Popen(
                    [
                        str(self.ruta_ejecutable),
                        "--model", str(self.ruta_modelo),
                        "--output-raw",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                
                stdout, stderr = proceso.communicate(input=texto.encode(), timeout=30)
                
                if proceso.returncode != 0:
                    raise RuntimeError(f"Piper falló: {stderr.decode()}")
                
                registro.info("Audio sintetizado en memoria: %d bytes", len(stdout))
                return stdout
                
            except subprocess.TimeoutExpired:
                proceso.kill()
                raise RuntimeError("Piper excedió el tiempo de espera")
            except FileNotFoundError:
                raise RuntimeError(
                    f"Ejecutable de Piper no encontrado: {self.ruta_ejecutable}"
                )
