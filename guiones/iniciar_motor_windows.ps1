# Script para iniciar el motor en Windows

Write-Host "=== Iniciando Motor de VisualMemory ===" -ForegroundColor Cyan
Write-Host ""

if (!(Test-Path ".venv_motor\Scripts\python.exe")) {
    Write-Host "Error: Entorno virtual del motor no encontrado" -ForegroundColor Red
    Write-Host "Ejecuta primero la instalacion" -ForegroundColor Yellow
    exit 1
}

Write-Host "Verificando CUDA..." -ForegroundColor Yellow
$cudaCheck = & .venv_motor\Scripts\python.exe -c "import torch; assert torch.cuda.is_available(), 'CUDA no disponible'; x=torch.ones(1, device='cuda'); torch.cuda.synchronize(); print(torch.cuda.get_device_name(0))" 2>&1
if ($LASTEXITCODE -eq 0) {
    $gpuName = $cudaCheck | Select-Object -Last 1
    Write-Host "CUDA disponible: $gpuName" -ForegroundColor Green
} else {
    Write-Host "CUDA no puede ejecutar kernels - usando CPU (sera mas lento)" -ForegroundColor Yellow
    Write-Host $cudaCheck -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "Iniciando servidor FastAPI en http://127.0.0.1:8765..." -ForegroundColor Green
Write-Host ""
Write-Host "NOTA: La primera vez puede tardar 10-15 minutos descargando modelos" -ForegroundColor Yellow
Write-Host "      (Qwen2.5-VL-3B ~7GB + Whisper Small ~500MB)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Presiona Ctrl+C para detener el motor" -ForegroundColor Gray
Write-Host ""

& .venv_motor\Scripts\python.exe -m uvicorn motor.principal:aplicacion --host 127.0.0.1 --port 8765
