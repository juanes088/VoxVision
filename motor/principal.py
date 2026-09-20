from fastapi import FastAPI

from motor.api.rutas_estado import rutas as rutas_estado
from motor.api.rutas_voz import rutas as rutas_voz

aplicacion = FastAPI(title="Visual Memory", version="1.0.0")
aplicacion.include_router(rutas_estado)
aplicacion.include_router(rutas_voz)
