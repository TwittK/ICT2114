# threads/reader.py
import cv2
import time
import shared.state as shared_state


def read_frames(use_ip_camera, camera_ip, channel):
    # global running, cap, frame_queue

    if use_ip_camera:
        # Camera config
        username = "admin"
        password = "Sit12345"
        # last digit of channel: Use 1 for main stream (better qual, but more bandwidth), 2 for sub stream
        rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/Streaming/Channels/{channel}"

        # Initialize IP camera instead of webcam
        shared_state.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

        # Check if camera connection is successful
        if not (shared_state.cap).isOpened():
            print("Failed to connect to the RTSP stream.")
            print(f"Attempted URL: {rtsp_url}")
            return

        print(f"✅ Successfully connected to IP camera: {camera_ip}")
    else:
        shared_state.cap = cv2.VideoCapture(0)  # to test with webcam

    while shared_state.running:
        ret, frame = (shared_state.cap).read()
        if not ret:
            print("Failed to read frame from IP camera")
            time.sleep(0.1)  # Wait a bit before retrying
            continue

        if not (shared_state.frame_queue).full():
            (shared_state.frame_queue).put(frame)
        time.sleep(0.01)

    (shared_state.cap).release()
    print("IP camera connection closed")
