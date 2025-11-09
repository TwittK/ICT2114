# shared/camera_manager.py
import threading, psycopg2, os
from shared.detection_manager import DetectionManager
from threads.saver import Saver

target_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]


class CameraManager:
  """
  Singleton class for managing all active cameras in the system.

  The CameraManager is responsible for:  
  - Initializing and maintaining a pool of camera objects.  
  - Starting and stopping all camera-related processing threads (e.g., reading, detection).  
  - Managing resources such as detection workers and saver threads.  

  This class follows the Singleton design pattern to ensure only one instance exists
  throughout the application lifecycle. Use `CameraManager.get_instance()` to retrieve 
  the active instance after initialization.

  Attributes:
    camera_pool (dict): A mapping of camera_id to camera instance and its associated threads.
    db (psycopg2.extensions.connection): Active PostgreSQL database connection.
    detection_manager (DetectionManager): Manager for coordinating YOLO detection workers.
    saver (Saver): Thread responsible for saving detection results.
  """
  _instance = None

  # Singleton
  def __new__(cls, db_params):
    if cls._instance is None:
      cls._instance = super(CameraManager, cls).__new__(cls)
      cls._instance._initialized = False
      cls._instance._ready_to_process = False
    return cls._instance
  
  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      raise RuntimeError("CameraManager has not been initialized yet.")
    return cls._instance

  def __init__(self, db_params):
    """
    Initializes a Camera Manager and prepares all cameras for detection.

    Gets all cameras from the database, starts detection threads on each of them.
    Stores references of all cameras in its camera pool for management.

    Parameters:
      db_params (dict): A dictionary containing parameters required to connect to the PostgreSQL database.
    """
    
    if self._initialized: # Singleton
      return 
    
    self.camera_pool = {}
    self.db = psycopg2.connect(**db_params)
    self._ready_to_process = False  # Initialize flag

    # Select all existing cameras
    cursor = self.db.cursor()
    cursor.execute("SELECT CameraId, ip_address FROM Camera;")
    rows = cursor.fetchall()
    cursor.close()

    gpu_count = os.getenv("GPU_COUNT")
    self.detection_manager = DetectionManager(gpu_count)
    self.saver = Saver()
    self.nvr_face_lock = threading.Lock()

    # Start detection on all cameras and add them to the camera pool
    for camera_id, ip_address in rows:
      # self.add_new_camera(camera_id, ip_address, True)
      # Overwrite the IP cameras within the database as a test camera
      print(f"[INFO] Overwriting camera {camera_id} as test dataset camera.")
      self.add_new_camera(camera_id, ip_address, True, use_dataset=True, dataset_path="./datasets/")

    self._initialized = True
  
  def shutdown_all_cameras(self):
    """
    Gracefully shuts down all active cameras in the camera pool.
    Ensures that all camera threads are properly terminated.
    Also stops all other threads (Detection Worker and Saver) for a clean exit.

    For each camera, this method:  
    - Clears the 'running' event to stop detection.  
    - Join all associated threads.  
    """

    for camera_id, camera_info in self.camera_pool.items():
      # Stop functions in threads.
      camera = camera_info.get("camera")
      if camera:
        camera.running.clear()

      # Stop all threads of camera.
      threads = camera_info.get("threads", {})
      for thread_name, thread in threads.items():
        thread.join(timeout=2)
        print(f"[INFO] Thread '{thread_name}' for camera {camera_id} joined.")

    self.detection_manager.stop_all()
    self.saver.stop()

  def remove_camera(self, camera_id):
    """
    Removes a camera from the camera pool and gracefully shuts it down.

    This method performs the following steps:  
    - Checks if the camera exists in the pool.  
    - Signals the detection to stop by clearing the 'running' event.  
    - Joins each thread.  
    - Deletes the camera entry from the camera pool.  

    Parameters:
      camera_id (int): The unique identifier of the camera to remove.

    Returns:
      bool: True if the camera was successfully removed, False if it was not found or error.
    """
    
    if camera_id not in self.camera_pool:
      print(f"[ERROR] Camera {camera_id} is not running.")
      return False

    # Stop functions in threads.
    camera = self.camera_pool[camera_id]["camera"]
    if camera:
      camera.running.clear()

    # Stop all threads of camera.
    camera_threads = self.camera_pool[camera_id]["threads"]
    for thread_name, thread in camera_threads.items():
      thread.join(timeout=2)
      print(f"[INFO] Thread '{thread_name}' for camera {camera_id} joined.")

    del self.camera_pool[camera_id]
    return True

  def add_new_camera(self, camera_id, ip_address, use_ip_camera, channel="101", use_dataset=False, dataset_path=None):
    """
    Adds a new camera and starts its associated processing/ detection threads.

    This method:  
    - Instantiates a Camera object.  
    - Starts threads for reading, processing, and saving frames.  
    - Stores the camera and its threads in the camera pool.  

    Parameters:
      camera_id (int): Unique identifier for the camera.
      ip_address (str): IP address of the camera.
      use_ip_camera (bool): Whether the camera is an IP camera or not. Use False only for testing purposes, otherwise it should always be True.
      channel (str, optional): Camera channel number. Defaults to "101".

    Returns:
      bool: True if the camera was added successfully, False otherwise.
    """
    from threads.reader import read_frames
    from threads.association import association
    from shared.camera import Camera

    try:
      camera = Camera(camera_id, ip_address, channel, use_ip_camera, self, use_dataset=use_dataset, dataset_path=dataset_path)

      # Start all threads
      read_thread = threading.Thread(target=read_frames, args=(camera,))
      association_thread = threading.Thread(target=association, args=(camera,))

      read_thread.start()
      association_thread.start()

      self.camera_pool[camera_id] = {
        "camera": camera,
        "threads": {
          "read": read_thread,
          "association": association_thread
        },
      }

      print(f"[INFO] Camera {camera_id} added.")
      return True

    except Exception:
      return False
    
  def set_initialized(self):
        """Signal that the system is ready to process frames"""
        self._ready_to_process = True
        print("[INFO] Camera Manager is now ready to process frames")

  def is_initialized(self):
      """Check if the system is ready to process frames"""
      return self._ready_to_process