# Navigate to the project root (two levels up from scripts)
Set-Location -Path (Join-Path $PSScriptRoot "..\..")

# Check if virtual environment is active
if (-not $env:VIRTUAL_ENV) {
    Write-Host "Virtual environment is NOT active. Activating..."
    .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "Virtual environment is already active at $env:VIRTUAL_ENV"
}

# Navigate to the modularized folder
Set-Location -Path "modularized"

# Run the Python application
python app.py
