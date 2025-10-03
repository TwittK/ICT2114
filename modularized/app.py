# app.py
import os
import secrets
import sys
import time

from dotenv import load_dotenv

# Add project root to sys.path so imports work correctly
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Absolute imports (no relative imports)
from threads.server import setup_app
from web.routes import app
from shared.camera_manager import CameraManager

# Create folders for faces and incompliances
os.makedirs(os.path.join("web", "static", "incompliances"), exist_ok=True)
os.makedirs("yolo_models", exist_ok=True)

# Load environment variables from .env
load_dotenv()

DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

# Set Flask secret key
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


def start_camera_manager():
    """Initialise camera detection in a background thread."""
    time.sleep(3)  # Give time to initialize database

    camera_manager = CameraManager(
        DB_PARAMS
    )  # Start detection on all cameras stored in database

    try:
        while True:
            time.sleep(0.01)
    finally:
        camera_manager.shutdown_all_cameras()
        print("[INFO] Camera manager shut down cleanly.")


if __name__ == "__main__":

    try:
        # Initialise database and defaults
        setup_app()

        # Start detection on all cameras stored in database
        camera_manager = CameraManager(DB_PARAMS)

        print("[INFO] Flask server started and all cameras in database started detection")

        # Run Flask in main thread for hot reload
        app.run(host="0.0.0.0", port=5000, debug=True)

    except KeyboardInterrupt:
        print("[INFO] Shutting down.")

    finally:
        print("[END] Exited cleanly.")
