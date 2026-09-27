from fastapi import FastAPI

from motor.api.rutas_estado import rutas as rutas_estado
from motor.api.rutas_voz import rutas as rutas_voz

app = FastAPI(title="VoxVision", version="1.0.0")
app.include_router(rutas_estado)
app.include_router(rutas_voz)
