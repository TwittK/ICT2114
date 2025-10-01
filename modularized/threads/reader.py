# threads/reader.py
import cv2
import time
from shared.camera import Camera

def read_frames(context: Camera):
    """
    Continuously reads frames from a camera source (IP camera or local webcam) and enqueues them for preprocessing.

    Implements reconnection logic with exponential backoff for IP cameras when frame reading fails repeatedly.

    Parameters:
        context (Camera): A Camera object containing camera configuration and state, including:
            - use_ip_camera (bool): Whether to use an IP camera (True) or local webcam (False, for testing only).
            - ip_address (str): IP address of the IP camera.
            - channel (str): Channel for the IP camera.
            - running (threading.Event): Event flag controlling the reading loop.
            - cap (cv2.VideoCapture): OpenCV video capture object.
            - manager (CameraManager): Reference to the central manager, to access shared queues.
            - frame_queue (queue.Queue): Local queue for buffering frames.
    
    Behavior:
        - Opens video capture based on whether IP camera or webcam is used.
        - Reads frames in a loop while the `running` event is set.
        - On frame read failure, counts consecutive failures.
        - For IP cameras, attempts to reconnect after multiple failures with exponential backoff.
        - Successfully read frames are put into the preprocessing queue of the manager.
        - Releases video capture on termination.

    """
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
            (context.frame_queue).put(frame)
        time.sleep(0.01)

    if context.cap:
        context.cap.release()
    print(f"📹 Camera {context.ip_address} connection closed")
