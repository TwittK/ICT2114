#!/bin/bash

# Get the parent directory of the 'scripts' folder (this script's location)
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(dirname "$script_dir")"

# Change to project root directory
cd "$project_root" || { echo "❌ Failed to change directory to $project_root"; exit 1; }

# Run docker compose with build and detached mode
sudo docker compose up --build -d

# Notify completion
echo -e "✅ Docker Compose started with --build -d in $project_root"
