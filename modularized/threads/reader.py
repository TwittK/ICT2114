# threads/reader.py
import cv2
import time
from shared.state import frame_queue, running, cap as shared_cap

def read_frames():
    # global running, cap, frame_queue
    global shared_cap

    shared_cap = cv2.VideoCapture(1)  # or replace with your video source
    while running:
        ret, frame = shared_cap.read()
        if not ret:
            continue
        
        if not frame_queue.full():
            frame_queue.put(frame)
        time.sleep(0.01)
    shared_cap.release()
