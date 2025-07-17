# threads/reader.py
import cv2
import time
from shared.camera import Camera


def read_frames(context: Camera):

    if context.use_ip_camera:
        # Camera config
        username = "admin"
        password = "Sit12345"
        # last digit of channel: Use 1 for main stream (better qual, but more bandwidth), 2 for sub stream
        # rtsp_url = f"rtsp://{username}:{password}@{context.camera_ip}/Streaming/Channels/{context.channel}"
        rtsp_url = f"rtsp://{username}:{password}@{context.ip_address}/Streaming/Channels/{context.channel}"

        # Initialize IP camera instead of webcam
        context.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

        # Check if camera connection is successful
        if not (context.cap).isOpened():
            print("Failed to connect to the RTSP stream.")
            print(f"Attempted URL: {rtsp_url}")
            return

        print(f"✅ Successfully connected to IP camera: {context.ip_address}")
    else:
        context.cap = cv2.VideoCapture(0)  # to test with webcam

    while context.running.is_set():
        ret, frame = (context.cap).read()
        if not ret:
            print("Failed to read frame from IP camera")
            time.sleep(0.1)  # Wait a bit before retrying
            continue

        if not (context.frame_queue).full():
            (context.frame_queue).put(frame)
        time.sleep(0.01)

    (context.cap).release()
    print("IP camera connection closed")
