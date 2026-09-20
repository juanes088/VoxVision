from contextlib import contextmanager
from contextvars import ContextVar
from threading import Condition


class GestorInferencia:
    def __init__(self):
        self._condicion = Condition()
        self._ocupada = False
        self._esperando_interactivas = 0
        self._prioridad: ContextVar[str] = ContextVar("prioridad_inferencia", default="interactiva")

    @contextmanager
    def prioridad_interactiva(self):
        token = self._prioridad.set("interactiva")
        try:
            yield
        finally:
            self._prioridad.reset(token)

    @contextmanager
    def prioridad_fondo(self):
        token = self._prioridad.set("fondo")
        try:
            yield
        finally:
            self._prioridad.reset(token)

    @contextmanager
    def reservar_gpu(self):
        # Una sola cola evita picos de VRAM. Los ciclos de vigilancia ceden el
        # siguiente turno a una consulta humana que ya este esperando.
        interactiva = self._prioridad.get() == "interactiva"
        with self._condicion:
            if interactiva:
                self._esperando_interactivas += 1
            try:
                while self._ocupada or (not interactiva and self._esperando_interactivas > 0):
                    self._condicion.wait()
                self._ocupada = True
            finally:
                if interactiva:
                    self._esperando_interactivas -= 1

        try:
            yield
        finally:
            with self._condicion:
                self._ocupada = False
                self._condicion.notify_all()
