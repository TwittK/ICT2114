# app.py
import threading
import os, time
from ultralytics import YOLO
from shared.state import running, cap

from threads.reader import read_frames
from threads.preprocessor import preprocess
from threads.detector import detection
from threads.saver import image_saver
from threads.server import run_app

# Create folders for faces and incompliances
os.makedirs(os.path.join("static", "faces"), exist_ok=True)
os.makedirs(os.path.join("static", "incompliances"), exist_ok=True)
os.makedirs("yolo_models", exist_ok=True)

model = YOLO(os.path.join("yolo_models", "yolo11m.pt"))
pose_model = YOLO(os.path.join("yolo_models", "yolov8n-pose.pt"))
food_beverage_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]

if __name__ == "__main__":

    try:
        read_thread = threading.Thread(target=read_frames)
        inference_thread = threading.Thread(target=preprocess, args=(model, pose_model, food_beverage_class_list, 0.3), daemon=True)
        detection_thread = threading.Thread(target=detection)
        save_thread = threading.Thread(target=image_saver, daemon=True)
        flask_thread = threading.Thread(target=run_app, daemon=True)

        read_thread.start()
        inference_thread.start()
        detection_thread.start()
        save_thread.start()
        flask_thread.start()

        try:
            while running:
                time.sleep(1)
                # pass
        except KeyboardInterrupt:
            running = False

        read_thread.join()
        detection_thread.join()

    finally:
        running = False
        cap.release()

        print(f"[END]")