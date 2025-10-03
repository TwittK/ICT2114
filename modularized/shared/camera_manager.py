# shared/camera_manager.py
import threading, psycopg2
from shared.model import ObjectDetectionModel

target_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]


class CameraManager:
  _instance = None

  # Singleton
  def __new__(cls, db_params):
    if cls._instance is None:
      cls._instance = super(CameraManager, cls).__new__(cls)
      cls._instance._initialized = False
    return cls._instance
  
  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      raise RuntimeError("CameraManager has not been initialized yet.")
    return cls._instance

  def __init__(self, db_params):
    from shared.detection_manager import DetectionManager

    if self._initialized: # Singleton
      return 
    
    self.camera_pool = {}
    self.db = psycopg2.connect(**db_params)

    # Select all existing cameras
    cursor = self.db.cursor()
    cursor.execute("SELECT CameraId, ip_address FROM Camera;")
    rows = cursor.fetchall()
    cursor.close()
    
    workers_count = 1
    self.detection_manager = DetectionManager(workers_count)

    # Start detection on all cameras and add them to the camera pool
    for camera_id, ip_address in rows:
      self.add_new_camera(camera_id, ip_address, True) 

    self._initialized = True
  
  def shutdown_all_cameras(self):
    """
    Gracefully shuts down all active cameras in the camera pool.
    Ensures that all camera threads are properly terminated.

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

  def add_new_camera(self, camera_id, ip_address, use_ip_camera, channel="101"):
    """
    Adds a new camera and starts its associated processing/ detection threads.

    This method:
    - Instantiates a Camera object.
    - Starts threads for reading, preprocessing, detection, and saving frames.
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
    #from threads.preprocessor import preprocess
    from threads.detector import detection
    from threads.saver import image_saver
    from shared.camera import Camera

    try:
      camera = Camera(camera_id, ip_address, channel, use_ip_camera, self)

      # Start all threads for detection
      read_thread = threading.Thread(target=read_frames, args=(camera,))
      #preprocess_thread = threading.Thread(target=preprocess, args=(camera, target_class_list, 0.3))
      detection_thread = threading.Thread(target=detection, args=(camera,))
      save_thread = threading.Thread(target=image_saver, args=(camera,))


      read_thread.start()
      #preprocess_thread.start()
      detection_thread.start()
      save_thread.start()

      self.camera_pool[camera_id] = {
        "camera": camera,
        "threads": {
          "read": read_thread,
          "detection": detection_thread,
          "save": save_thread,
          #"preprocess": preprocess_thread
        },
      }

      print(f"[INFO] Camera {camera_id} added.")
      return True

    except Exception:
      return False
