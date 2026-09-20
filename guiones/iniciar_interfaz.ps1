$ErrorActionPreference = "Stop"

Write-Host "=== Iniciando Interfaz Visual Memory ===" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path ".venv_interfaz\Scripts\python.exe")) {
    Write-Host "Error: Entorno virtual de la interfaz no encontrado" -ForegroundColor Red
    Write-Host "Ejecuta primero la instalacion" -ForegroundColor Yellow
    exit 1
}

Write-Host "Verificando motor..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8765/estado" -TimeoutSec 2 -ErrorAction Stop
    Write-Host "Motor conectado" -ForegroundColor Green
} catch {
    Write-Host "Motor no responde. Asegurate de iniciarlo primero:" -ForegroundColor Yellow
    Write-Host "   powershell -ExecutionPolicy Bypass -File guiones\iniciar_motor_windows.ps1" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Continuar de todos modos? (S/N)" -ForegroundColor Yellow
    $continue = Read-Host
    if ($continue -ne "S" -and $continue -ne "s") {
        exit 0
    }
}

Write-Host ""
Write-Host "Iniciando interfaz..." -ForegroundColor Green
& ".venv_interfaz\Scripts\python.exe" -m interfaz.principal
