# threads/reader.py
import cv2
import time
from shared.camera import Camera


def read_frames(context: Camera):
    """
    Reads frames from an IP camera or webcam and handles reconnections in case of failure.

    This function runs in a thread that continuously reads frames from the camera and handles connection issues by
    attempting to reconnect if frames cannot be retrieved. If the camera is an IP camera, it uses
    RTSP to stream frames, and it supports retries up to a maximum number of attempts with exponential backoff if consecutive failures occur.
    For non-IP cameras such as a local webcam, it directly captures frames (Use webcam only for testing on personal machines).

    Parameters:
        context (Camera): The camera context, containing configuration and state information about
                           the camera, such as whether it is an IP camera, its IP address, channel,
                           and the frame queue for processing.

    Notes:
        - For IP cameras, the function uses RTSP for video streaming with basic authentication.
        - The function uses exponential backoff for retrying failed connections, gradually increasing the
          delay between each reconnection attempt.
        - The function supports a maximum retry limit to prevent endless retries and control the backoff behavior.
    """
    max_retries = 30  # Maximum reconnection attempts
    retry_delay = 1.0  # Initial delay between retries
    max_delay = 10.0  # Maximum delay between retries

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

        print(f"[DEBUG NVR CHECK] Attempted URL: {rtsp_url}")
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
                print(
                    f"⚠️ Failed to read frame from IP camera {context.ip_address} (attempt {consecutive_failures})"
                )
            elif consecutive_failures <= 5:
                print(
                    f"⚠️ Still failing to read frames (attempt {consecutive_failures})"
                )
            elif consecutive_failures == 10:
                print(
                    f"🔄 Camera {context.ip_address} may be reconfiguring, attempting reconnection..."
                )

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
                        print(
                            f"❌ Exceeded maximum retry attempts for camera {context.ip_address}"
                        )
                        break
            else:
                time.sleep(0.1)  # Short delay for non-IP cameras or initial failures

            continue

        # Successfully read frame
        if consecutive_failures > 0:
            print(
                f"✅ Camera {context.ip_address} connection restored after {consecutive_failures} failed attempts"
            )
            consecutive_failures = 0
            current_delay = retry_delay

        if not (context.frame_queue).full():
            context.manager.detection_manager.submit(frame, context)
            # (context.frame_queue).put(frame)
        time.sleep(0.01)

    if context.cap:
        context.cap.release()
    print(f"📹 Camera {context.ip_address} connection closed")
