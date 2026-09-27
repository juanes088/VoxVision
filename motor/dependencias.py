from functools import lru_cache

from motor.configuracion import obtener_configuracion
from motor.vision.gestor_inferencia import GestorInferencia
from motor.voz.orquestador_conversacional import OrquestadorConversacional
from motor.voz.sintetizador_piper import SintetizadorPiper


@lru_cache(maxsize=1)
def obtener_orquestador_conversacional() -> OrquestadorConversacional:
    configuracion = obtener_configuracion()
    gestor = GestorInferencia()
    sintetizador = SintetizadorPiper(
        ruta_modelo=configuracion.ruta_modelo_piper,
        ruta_ejecutable=configuracion.ruta_ejecutable_piper,
    )
    return OrquestadorConversacional(
        configuracion=configuracion,
        gestor=gestor,
        sintetizador=sintetizador,
    )
