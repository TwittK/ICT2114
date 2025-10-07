# Get the parent directory of the 'scripts' folder.
$projectRoot = Split-Path $PSScriptRoot -Parent

# Change to project root (where docker-compose.yml is expected)
Set-Location -Path $projectRoot

# Run docker compose with build and detached mode.
docker compose up --build -d

# Notify completion.
Write-Host "✅ Docker Compose started with --build -d in $projectRoot" -ForegroundColor Green