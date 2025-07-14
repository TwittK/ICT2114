import threading
import queue
from shared.camera_manager import CameraManager

class Camera:
  def __init__(self, camera_id, ip_address, channel, use_ip_camera, manager: CameraManager):

    # Store Camera details
    self.camera_id = camera_id
    self.ip_address = ip_address
    self.channel = channel
    self.use_ip_camera = use_ip_camera
    self.manager = manager

    self.frame_queue = queue.Queue(maxsize=10)
    self.save_queue = queue.Queue(maxsize=10)
    self.process_queue = queue.Queue(maxsize=10)
    self.display_queue = queue.Queue(maxsize=10)

    self.cap = None

    # Shared flags and locks
    self.running = True
    self.detected_incompliance_lock = threading.Lock()
    self.pose_points_lock = threading.Lock()
    self.flagged_foodbev_lock = threading.Lock()

    self.flagged_foodbev = [] # Format: [track ids]
    self.pose_points = []
    self.detected_incompliance = {} # Format: { track_id, [coords(List Of 4 Values), center(Tuple Of 2 Values), confidence(Float), classId(Integer)] }

    # Track wrist proximity times per person
    self.wrist_proximity_history = {}  # Format: {track_id: [timestamps]}
