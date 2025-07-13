# app.py
import threading
import os, time
import shared.state as shared_state

from threads.reader import read_frames
from threads.preprocessor import preprocess
from threads.detector import detection
from threads.saver import image_saver
from threads.server import run_app

# Create folders for faces and incompliances
os.makedirs(os.path.join("web", "static", "faces"), exist_ok=True)
os.makedirs(os.path.join("web", "static", "incompliances"), exist_ok=True)
os.makedirs("yolo_models", exist_ok=True)

target_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]

# [39, 40, 41]
# just the drinks from coco dataset
# bread: 31, chips: 55, chocolate: 56, cookies: 67, desserts: 77, french fries: 86, hamburger: 100, ice-cream: 108, pastry: 156, waffles: 231
# food_class_list = [31, 55, 56, 67, 77, 86, 100, 108, 156, 231]

if __name__ == "__main__":

    try:
        read_thread = threading.Thread(target=read_frames, args=(True, "192.168.10.64", "101"))
        inference_thread = threading.Thread(
            target=preprocess,
            args=(target_class_list, 0.3),
            daemon=True,
        )
        detection_thread = threading.Thread(target=detection)
        save_thread = threading.Thread(target=image_saver)
        flask_thread = threading.Thread(target=run_app, daemon=True)

        read_thread.start()
        inference_thread.start()
        detection_thread.start()
        save_thread.start()
        flask_thread.start()

        while shared_state.running:
            time.sleep(1)

    except KeyboardInterrupt:
        shared_state.running = False
        shared_state.save_queue.put(None)
        read_thread.join()
        print("Read thread joined.")
        detection_thread.join()
        print("Detection thread joined.")
        save_thread.join()
        print("Save thread joined.")

    finally:
        shared_state.running = False
        print(f"[END] Exited cleanly.")
