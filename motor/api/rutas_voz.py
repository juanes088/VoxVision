import io
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image
from pydantic import BaseModel

from motor.dependencias import obtener_orquestador_conversacional
from motor.vision.realce import realzar_si_oscura

rutas = APIRouter(prefix="/voz", tags=["voz"])


class RespuestaConversacion(BaseModel):
    transcripcion: str
    respuesta: str
    ruta_audio: str


class RespuestaTexto(BaseModel):
    respuesta: str
    ruta_audio: str


@rutas.post("/iniciar-escucha")
async def iniciar_escucha(
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Inicia la captura de audio del micrófono."""
    orquestador.iniciar_escucha()
    return {"estado": "escuchando"}


@rutas.post("/detener-y-procesar", response_model=RespuestaConversacion)
async def detener_y_procesar(
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Detiene la captura y procesa la conversación completa."""
    transcripcion, respuesta, ruta_audio = await run_in_threadpool(
        orquestador.detener_y_procesar
    )
    return RespuestaConversacion(
        transcripcion=transcripcion,
        respuesta=respuesta,
        ruta_audio=str(ruta_audio),
    )


@rutas.post("/conversar", response_model=RespuestaTexto)
async def conversar(
    texto: str = Form(...),
    incluir_vision: bool = Form(True),
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Procesa texto directamente sin captura de audio."""
    respuesta, ruta_audio = await run_in_threadpool(
        orquestador.procesar_texto_directo,
        texto,
        incluir_vision,
    )
    return RespuestaTexto(
        respuesta=respuesta,
        ruta_audio=str(ruta_audio),
    )


@rutas.post("/actualizar-frame")
async def actualizar_frame(
    frame: UploadFile = File(...),
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Actualiza el frame actual para contexto visual."""
    contenido = await frame.read()
    # Forzar la carga y RGB: el frame se reutiliza segundos despues (captioner
    # de fondo y conversacion), cuando el BytesIO original ya no existe.
    with io.BytesIO(contenido) as flujo:
        imagen = Image.open(flujo).convert("RGB")
    # Realzar si la escena esta oscura: mejora conteo/observacion del modelo.
    imagen = realzar_si_oscura(imagen)
    orquestador.actualizar_frame(imagen)
    return {"estado": "frame actualizado"}


@rutas.post("/actualizar-frames")
async def actualizar_frames(
    frames: list[UploadFile] = File(...),
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Registra los keyframes elegidos por la interfaz para la proxima consulta."""
    imagenes = []
    for archivo in frames:
        contenido = await archivo.read()
        with io.BytesIO(contenido) as flujo:
            imagen = Image.open(flujo).convert("RGB")
        imagenes.append(realzar_si_oscura(imagen))
    orquestador.actualizar_frames(imagenes)
    return {"estado": "frames actualizados", "cantidad": len(imagenes)}


@rutas.post("/limpiar-historial")
async def limpiar_historial(
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Limpia el historial de conversación."""
    orquestador.limpiar_historial()
    return {"estado": "historial limpiado"}


@rutas.post("/proveedor")
async def establecer_proveedor(
    modo: str = Form(...),
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Cambia el proveedor de vision en caliente (claude / local)."""
    activo = await run_in_threadpool(orquestador.establecer_proveedor, modo)
    return {"proveedor": activo}


@rutas.get("/estado")
async def obtener_estado(
    orquestador=Depends(obtener_orquestador_conversacional),
):
    """Obtiene el estado actual del sistema de voz."""
    return {
        "escuchando": orquestador.esta_escuchando(),
        "memoria_visual": orquestador.buffer_visual.estado(),
        "proveedor": orquestador.proveedor_actual,
    }
