$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "No se encontro el lanzador de Python. Instala Python 3.11."
}

& py -3.11 -m venv .venv_interfaz
& .\.venv_interfaz\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
& .\.venv_interfaz\Scripts\python.exe -m pip install -r dependencias_interfaz.txt
