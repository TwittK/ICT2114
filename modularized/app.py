# app.py
import threading
import os, time

from threads.server import run_app
from shared.camera_manager import CameraManager

# Create folders for faces and incompliances
os.makedirs(os.path.join("web", "static", "incompliances"), exist_ok=True)
os.makedirs("yolo_models", exist_ok=True)

if __name__ == "__main__":

    try:

        flask_thread = threading.Thread(target=run_app, daemon=True)
        flask_thread.start()

        time.sleep(3) # Temp: give time to initialize database

        camera_manager = CameraManager("users.sqlite") # Start detection on all cameras stored in database

        print("[INFO] Flask server started and all cameras in database started detection")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("[INFO] Shutting down.")

    finally:
        print(f"[END] Exited cleanly.")
