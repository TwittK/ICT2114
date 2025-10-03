# app.py
import threading
import os, time
from dotenv import load_dotenv

from threads.server import run_app
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

if __name__ == "__main__":

    try:

        flask_thread = threading.Thread(target=run_app, daemon=True)
        flask_thread.start()

        time.sleep(3)  # Give time to initialize database

        camera_manager = CameraManager(
            DB_PARAMS
        )  # Start detection on all cameras stored in database

        print(
            "[INFO] Flask server started and all cameras in database started detection"
        )

        while True:
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("[INFO] Shutting down.")

    finally:
        camera_manager.shutdown_all_cameras()
        print("[END] Exited cleanly.")
