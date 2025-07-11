# threads/reader.py
import cv2
import time
from shared.state import frame_queue, running, cap as shared_cap


def read_frames(use_ip_camera, camera_ip, channel):
    # global running, cap, frame_queue
    global shared_cap

    if use_ip_camera:
        # Camera config
        username = "admin"
        password = "Sit12345"
        # last digit of channel: Use 1 for main stream (better qual, but more bandwidth), 2 for sub stream
        rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/Streaming/Channels/{channel}"

        # Initialize IP camera instead of webcam
        shared_cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

        # Check if camera connection is successful
        if not shared_cap.isOpened():
            print("Failed to connect to the RTSP stream.")
            print(f"Attempted URL: {rtsp_url}")
            return

        print(f"✅ Successfully connected to IP camera: {camera_ip}")
    else:
        shared_cap = cv2.VideoCapture(0)  # to test with webcam

    while running:
        ret, frame = shared_cap.read()
        if not ret:
            print("Failed to read frame from IP camera")
            time.sleep(0.1)  # Wait a bit before retrying
            continue

        if not frame_queue.full():
            frame_queue.put(frame)
        time.sleep(0.01)

    shared_cap.release()
    print("IP camera connection closed")
