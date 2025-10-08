# threads/reader.py
import cv2
import time
from shared.camera import Camera


# def read_frames(context: Camera):

#     if context.use_ip_camera:
#         # Camera config
#         username = "admin"
#         password = "Sit12345"
#         # last digit of channel: Use 1 for main stream (better qual, but more bandwidth), 2 for sub stream
#         # rtsp_url = f"rtsp://{username}:{password}@{context.camera_ip}/Streaming/Channels/{context.channel}"
#         rtsp_url = f"rtsp://{username}:{password}@{context.ip_address}/Streaming/Channels/{context.channel}"

#         # Initialize IP camera instead of webcam
#         context.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

#         # Check if camera connection is successful
#         if not (context.cap).isOpened():
#             print("Failed to connect to the RTSP stream.")
#             print(f"Attempted URL: {rtsp_url}")
#             return

#         print(f"✅ Successfully connected to IP camera: {context.ip_address}")
#     else:
#         context.cap = cv2.VideoCapture(0)  # to test with webcam

#     while context.running:
#         ret, frame = (context.cap).read()
#         if not ret:
#             print("Failed to read frame from IP camera")
#             time.sleep(0.1)  # Wait a bit before retrying
#             continue

#         if not (context.frame_queue).full():
#             (context.frame_queue).put(frame)
#         time.sleep(0.01)

#     (context.cap).release()
#     print("IP camera connection closed")

def read_frames(context: Camera):
    max_retries = 30  # Maximum reconnection attempts
    retry_delay = 1.0  # Initial delay between retries
    max_delay = 10.0   # Maximum delay between retries
    
    if context.use_ip_camera:
        # Camera config
        username = "admin"
        password = "Sit12345"
        rtsp_url = f"rtsp://{username}:{password}@{context.ip_address}/Streaming/Channels/{context.channel}"

        # Initialize IP camera
        context.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

        # Check if camera connection is successful
        if not (context.cap).isOpened():
            print("Failed to connect to the RTSP stream.")
            print(f"Attempted URL: {rtsp_url}")
            return

        print(f"✅ Successfully connected to IP camera: {context.ip_address}")
    else:
        context.cap = cv2.VideoCapture(0)  # to test with webcam

    consecutive_failures = 0
    current_delay = retry_delay

    while context.running.is_set():
        ret, frame = (context.cap).read()
        
        if not ret:
            consecutive_failures += 1
            
            if consecutive_failures == 1:
                print(f"⚠️ Failed to read frame from IP camera {context.ip_address} (attempt {consecutive_failures})")
            elif consecutive_failures <= 5:
                print(f"⚠️ Still failing to read frames (attempt {consecutive_failures})")
            elif consecutive_failures == 10:
                print(f"🔄 Camera {context.ip_address} may be reconfiguring, attempting reconnection...")
            
            # If we've failed multiple times, try to reconnect
            if consecutive_failures >= 10 and context.use_ip_camera:
                print(f"🔄 Attempting to reconnect to camera {context.ip_address}...")
                
                # Release current connection
                if context.cap:
                    context.cap.release()
                
                # Wait before reconnecting
                time.sleep(current_delay)
                
                # Try to reconnect
                username = "admin"
                password = "Sit12345"
                rtsp_url = f"rtsp://{username}:{password}@{context.ip_address}/Streaming/Channels/{context.channel}"
                
                context.cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                
                if context.cap.isOpened():
                    print(f"✅ Successfully reconnected to camera {context.ip_address}")
                    consecutive_failures = 0
                    current_delay = retry_delay  # Reset delay
                else:
                    print(f"❌ Failed to reconnect to camera {context.ip_address}")
                    # Exponential backoff
                    current_delay = min(current_delay * 1.5, max_delay)
                    
                    # If we've exceeded max retries, give up
                    if consecutive_failures >= max_retries:
                        print(f"❌ Exceeded maximum retry attempts for camera {context.ip_address}")
                        break
            else:
                time.sleep(0.1)  # Short delay for non-IP cameras or initial failures
            
            continue
        
        # Successfully read frame
        if consecutive_failures > 0:
            print(f"✅ Camera {context.ip_address} connection restored after {consecutive_failures} failed attempts")
            consecutive_failures = 0
            current_delay = retry_delay

        if not (context.frame_queue).full():
            context.manager.detection_manager.submit(frame, context)
            #(context.frame_queue).put(frame)
        time.sleep(0.01)

    if context.cap:
        context.cap.release()
    print(f"📹 Camera {context.ip_address} connection closed")
