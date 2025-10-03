#!/bin/bash

# Navigate to the project root (two levels up from scripts)
cd "$(dirname "$0")/../.." || exit

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Virtual environment is NOT active. Activating..."
    source .venv/bin/activate
else
    echo "Virtual environment is already active at $VIRTUAL_ENV"
fi

# Navigate to the modularized folder
cd modularized || exit

# Run the Python application
python app.py

