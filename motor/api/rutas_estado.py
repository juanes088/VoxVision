from fastapi import APIRouter

from motor.configuracion import obtener_configuracion

rutas = APIRouter(prefix="/estado", tags=["estado"])


@rutas.get("")
def obtener_estado() -> dict:
    """Health check simple para la interfaz."""
    configuracion = obtener_configuracion()
    return {
        "estado": "ok",
        "proveedor_vision": configuracion.proveedor_vision,
        "modelo": configuracion.modelo_qwen_vl,
    }
