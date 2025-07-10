# threads/reader.py
import cv2
import time
from shared.state import frame_queue, running, cap as shared_cap

NVR_IP = "192.168.1.63"


def read_frames():
    # global running, cap, frame_queue
    global shared_cap

    use_ip_camera = False

    if use_ip_camera:
        # # Camera config
        camera_ip = "192.168.10.64"
        username = "admin"
        password = "Sit12345"
        # Use 101 for main stream (better qual, but more bandwidth), 102 for sub stream
        rtsp_url = f"rtsp://{username}:{password}@{camera_ip}/Streaming/Channels/101"

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

    # Camera config
    # camera_ip = "192.168.1.64"
    username = "admin"
    password = "Sit12345"
    # Use 101 for main stream (better qual, but more bandwidth), 102 for sub stream
    rtsp_url = f"rtsp://{username}:{password}@{NVR_IP}/Streaming/channels/1501"

    # Initialize IP camera instead of webcam
    shared_cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    # Check if camera connection is successful
    if not shared_cap.isOpened():
        print("Failed to connect to the RTSP stream.")
        print(f"Attempted URL: {rtsp_url}")
        return

    print(f"✅ Successfully connected to IP camera: {NVR_IP}")

    # Optional: Set buffer size to reduce latency
    shared_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
