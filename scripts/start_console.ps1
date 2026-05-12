$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    python -m venv (Join-Path $ProjectRoot ".venv")
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -e "${ProjectRoot}[html]"
& $Python -m inbox_lens console
