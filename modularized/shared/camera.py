import threading
import queue
from shared.camera_manager import CameraManager

class Camera:
  """
  Represents a camera device and manages its detection pipelines.

  This class holds camera configuration, queues for inter-thread communication,
  and shared state such as event flags and locks used across multiple threads.

  Attributes:
    camera_id (int): Unique identifier for the camera.
    ip_address (str): IP address of the camera.
    channel (str): Camera channel number, e.g., "101".
    use_ip_camera (bool): Indicates if the camera is an IP camera. Use False only for testing purposes, otherwise it should always be True.
    manager (CameraManager): Reference to the parent camera manager instance.
    frame_queue (Queue): Queue for raw frames, used by YOLO object and pose detection.
    process_queue (Queue): Queue for frames for human to food/ drink association.
    save_queue (Queue): Queue for frames of incompliances to be saved.
    display_queue (Queue): Queue for frames to be displayed on the video feed in dashboard.
    running (threading.Event): Event flag to control the camera's processing threads.
    flagged_foodbev (list): Track IDs flagged for food/beverage policy violations.
    pose_points (list): List of detected pose keypoints per frame.
    detected_incompliance (dict): Tracks detected compliance violations by track ID.
    wrist_proximity_history (dict): Historical wrist proximity timestamps by track ID.
  """

  def __init__(self, camera_id, ip_address, channel, use_ip_camera, manager: CameraManager):

    # Store Camera details
    self.camera_id = camera_id
    self.ip_address = ip_address
    self.channel = channel
    self.use_ip_camera = use_ip_camera

    self.manager = manager
    self.detection_manager = manager.detection_manager

    self.frame_queue = queue.Queue(maxsize=10)
    self.save_queue = queue.Queue(maxsize=10)
    self.process_queue = queue.Queue(maxsize=10)
    self.display_queue = queue.Queue(maxsize=10)

    self.cap = None

    # Shared flags and locks
    self.running = threading.Event()
    self.running.set()
    
    self.detected_incompliance_lock = threading.Lock()
    self.pose_points_lock = threading.Lock()
    self.flagged_foodbev_lock = threading.Lock()

    self.flagged_foodbev = [] # Format: [track ids]
    self.pose_points = []
    self.detected_incompliance = {} # Format: { track_id, [coords(List Of 4 Values), center(Tuple Of 2 Values), confidence(Float), classId(Integer)] }

    # Track wrist proximity times per person
    self.wrist_proximity_history = {}  # Format: {track_id: [timestamps]}
