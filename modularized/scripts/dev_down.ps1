# Get the parent directory of the 'scripts' folder.
$projectRoot = Split-Path $PSScriptRoot -Parent

# Change to project root (where docker-compose.yml is expected)
Set-Location -Path $projectRoot

# Run docker compose down to stop and remove containers, networks, etc.
docker compose down

# Notify completion.
Write-Host "🛑 Docker Compose stopped (down) in $projectRoot" -ForegroundColor Yellow