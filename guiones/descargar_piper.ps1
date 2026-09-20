# Script para instalar Piper TTS en Windows

Write-Host "=== Instalación de Piper TTS en Windows ===" -ForegroundColor Cyan
Write-Host ""

# Crear directorios
New-Item -ItemType Directory -Force -Path "modelos\piper" | Out-Null
New-Item -ItemType Directory -Force -Path "bin" | Out-Null

# URL de releases de Piper
$PIPER_VERSION = "2023.11.14-2"
$PIPER_URL = "https://github.com/rhasspy/piper/releases/download/$PIPER_VERSION/piper_windows_amd64.zip"

Write-Host "Descargando Piper para Windows..." -ForegroundColor Yellow
$piperZip = "$env:TEMP\piper.zip"
Invoke-WebRequest -Uri $PIPER_URL -OutFile $piperZip

Write-Host "Extrayendo Piper..." -ForegroundColor Yellow
Expand-Archive -Path $piperZip -DestinationPath "bin\" -Force
Remove-Item $piperZip

Write-Host "Piper instalado en: bin\piper.exe" -ForegroundColor Green
Write-Host ""

# Descargar modelo de voz en español
Write-Host "Descargando modelo de voz en español (es_ES-claude-medium)..." -ForegroundColor Yellow

$VOICE_URL_BASE = "https://github.com/rhasspy/piper/releases/download/v1.0.0"
$VOICE_NAME = "es_ES-claude-medium"

# Descargar .onnx
Write-Host "Descargando ${VOICE_NAME}.onnx..." -ForegroundColor Yellow
Invoke-WebRequest -Uri "$VOICE_URL_BASE/${VOICE_NAME}.onnx" `
    -OutFile "modelos\piper\${VOICE_NAME}.onnx"

# Descargar .onnx.json (config)
Write-Host "Descargando ${VOICE_NAME}.onnx.json..." -ForegroundColor Yellow
Invoke-WebRequest -Uri "$VOICE_URL_BASE/${VOICE_NAME}.onnx.json" `
    -OutFile "modelos\piper\${VOICE_NAME}.onnx.json"

Write-Host ""
Write-Host "✅ Piper instalado exitosamente" -ForegroundColor Green
Write-Host ""
Write-Host "Puedes probar con:" -ForegroundColor Cyan
Write-Host "  echo 'Hola mundo' | .\bin\piper.exe --model modelos\piper\${VOICE_NAME}.onnx --output_file test.wav"
Write-Host ""
Write-Host "Actualiza tu .env con:" -ForegroundColor Cyan
Write-Host "  RUTA_MODELO_PIPER=modelos/piper/${VOICE_NAME}.onnx"
Write-Host "  RUTA_EJECUTABLE_PIPER=bin/piper.exe"
