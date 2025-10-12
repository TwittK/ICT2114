import threading
import queue

class Camera:
  """
  Represents a camera device and manages its detection pipelines.

  This class holds camera configuration, queues, shared state such as event flags, and locks used across multiple threads.

  Attributes:
    camera_id (int): Unique identifier for the camera.
    ip_address (str): IP address of the camera.
    channel (str): Channel identifier (e.g., "1501, 101, 1601, 201").
    use_ip_camera (bool): Indicates if the camera is an IP camera. Set to False only for testing with webcam.
    manager (CameraManager): Reference to the parent CameraManager instance.
    detection_manager: Inference manager retrieved from the camera manager.

    frame_queue (queue.Queue): Queue for raw frames to use in object and pose detection.
    process_queue (queue.Queue): Queue for frames used in association logic (human-to-food/beverage).
    display_queue (queue.Queue): Queue for frames to be displayed in the dashboard UI.

    running (threading.Event): Flag to control camera's detection loop.

    flagged_foodbev (list): List of track IDs flagged for food or beverage policy violations.
    pose_points (list): List of detected pose keypoints per frame.
    detected_incompliance (dict): Maps track IDs to non-compliant detection data.
      Format: {
        track_id: [coords (list of 4), center (tuple), confidence (float), class_id (int)]
      }

    wrist_proximity_history (dict): Historical record of wrist proximity timestamps by track ID.
      Format: {
        track_id: [timestamp1, timestamp2, ...]
      }

    detected_incompliance_lock (threading.Lock): Lock for accessing/modifying 'detected_incompliance'.
    pose_points_lock (threading.Lock): Lock for accessing/modifying 'pose_points'.
    flagged_foodbev_lock (threading.Lock): Lock for accessing/modifying 'flagged_foodbev'.
  """

  def __init__(self, camera_id, ip_address, channel, use_ip_camera, manager):
    
    # Store Camera details
    self.camera_id = camera_id
    self.ip_address = ip_address
    self.channel = channel
    self.use_ip_camera = use_ip_camera

    self.manager = manager
    self.detection_manager = manager.detection_manager

    self.frame_queue = queue.Queue(maxsize=10)
    self.process_queue = queue.Queue(maxsize=10)
    self.display_queue = queue.Queue(maxsize=3)

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
