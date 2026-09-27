# Arquitectura

Asistente conversacional por voz con visión. Dos procesos que hablan por HTTP.

```
Windows: Interfaz (PySide6)                 Motor (FastAPI)
  - Camara (OpenCV)                            /voz/iniciar-escucha
  - Microfono                                  /voz/detener-y-procesar
  - Captura + seleccion de keyframes  --HTTP-> /voz/actualizar-frames
  - Selector de modo (API/Local)               /voz/proveedor
  - Reproduccion de audio                       /estado
```

## Flujo de una interacción (voz)

1. **Interfaz**: al pulsar "Hablar por audio" captura frames de la cámara a
   ~4 fps y arranca el micrófono.
2. Al soltar, selecciona los **keyframes** relevantes por clustering de
   histogramas de color (VSUMM, `interfaz/seleccion_frames.py`), los anima y los
   envía al motor.
3. **Motor**: transcribe el audio con **Whisper**, manda los frames + el texto
   al **VLM** activo (Claude por API o Qwen local) y sintetiza la respuesta con
   **Piper**.
4. La interfaz reproduce el audio.

## Componentes del motor

- `motor/voz/transcritor_whisper.py` — STT (Whisper).
- `motor/voz/conversador_claude.py` — VLM por API (Claude vía aiapiflow).
- `motor/voz/conversador_qwen.py` — VLM local (Qwen2.5-VL 3B, int4).
- `motor/voz/sintetizador_piper.py` — TTS (Piper).
- `motor/voz/texto_voz.py` — limpia el texto para la voz (sin markdown ni emojis).
- `motor/voz/orquestador_conversacional.py` — encadena todo y elige proveedor.
- `motor/vision/gestor_inferencia.py` — serializa el uso de GPU.
- `motor/vision/realce.py` — realza frames oscuros antes de la inferencia.

## Proveedor de visión

Conmutable en caliente desde la interfaz (`/voz/proveedor`):

| Modo | Modelo | Imágenes por consulta | Notas |
|------|--------|----------------------|-------|
| API (Claude) | claude-sonnet-5 | hasta 5 | mejor calidad |
| Local | Qwen2.5-VL 3B int4 | 1 | offline, menos preciso |

## Decisiones

- Interfaz y motor separados; la selección de frames vive en la interfaz para
  poder visualizarla y para no cargar la GPU del motor.
- Al responder, el modelo recibe pocos keyframes, no un vídeo entero: latencia
  acotada.
- Whisper y Piper siempre locales; solo la visión puede salir a una API.
- Las claves se inyectan por `.env` y nunca se guardan en el repositorio.
