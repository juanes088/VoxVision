# VoxVision

Asistente de voz que ademas ve por la camara. La idea es hablarle y que responda
teniendo en cuenta lo que le muestras. Por ejemplo le muestro el celular y le
pregunto de que color es, y me contesta por voz.

Lo hice para aprender a conectar varias cosas (voz a texto, un modelo de vision
y texto a voz). Es un prototipo, funciona pero no esta listo para produccion.

## Como funciona

Son dos programas separados que se hablan por HTTP:

- el motor (FastAPI): hace la parte pesada. Pasa el audio a texto con Whisper,
  le manda la imagen y el texto a un modelo de vision, y genera la voz con Piper.
- la interfaz (PySide6): muestra la camara, graba cuando aprietas el boton,
  elige unos frames y reproduce la respuesta.

El modelo de vision se puede cambiar desde la interfaz: Claude (por API, va mejor
pero necesita una key) o Qwen2.5-VL 3B corriendo local en la GPU. Whisper y Piper
siempre son locales.

## Requisitos

- Python 3.11
- GPU Nvidia (yo lo corri en una RTX 5060 de 8GB)
- microfono y camara
- Piper con una voz en español (archivos .onnx)
- una API key si vas a usar el modo por API

## Instalacion

Se usan dos entornos virtuales, uno para el motor y otro para la interfaz.

```
python -m venv .venv_motor
python -m venv .venv_interfaz

.venv_motor\Scripts\python -m pip install -r dependencias_motor.txt
.venv_interfaz\Scripts\python -m pip install -r dependencias_interfaz.txt
```

Si tienes una GPU RTX 50xx hay que instalar torch de CUDA 12.8 antes que el resto
(el comando esta anotado dentro de dependencias_motor.txt).

Los modelos (Piper y Qwen) no estan en el repo por el peso, hay que bajarlos
aparte. En guiones/ hay un script para Piper, y el Qwen se baja de Hugging Face
a modelos/qwen2.5-vl-3b.

## Configuracion

Copia .env.ejemplo a .env y llenalo con tus datos: la API key, la ruta donde
quedo Piper, y si quieres usar claude o local en PROVEEDOR_VISION. El .env no se
sube al repo porque tiene las claves.

## Correrlo

Primero el motor y despues la interfaz, en dos terminales:

```
.venv_motor\Scripts\python -m uvicorn motor.principal:aplicacion --host 127.0.0.1 --port 8765
.venv_interfaz\Scripts\python -m interfaz.principal
```

Cuando abra la interfaz aprietas "Hablar por audio", dices algo mostrando lo que
quieras a la camara y sueltas.

## Notas

Con el modo por API responde bastante bien. Con el 3B local a veces se equivoca y
la latencia depende del hardware y de la conexion. Si algo no arranca casi
siempre es tema de CUDA/torch o que Piper no esta en la ruta del .env.
