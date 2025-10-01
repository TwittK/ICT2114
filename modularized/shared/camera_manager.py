# shared/camera_manager.py
import threading, psycopg2, queue
from concurrent.futures import ThreadPoolExecutor
from threads.model import ObjectDetectionModel, PoseDetectionModel, ImageClassificationModel

target_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]
SENTINEL = object()

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

    if self._initialized: # Singleton
      return 
    
    self.camera_pool = {}
    self.db = psycopg2.connect(**db_params)

    # Shared queues for all cameras
    self.preprocess_queue = queue.Queue()
    self.detection_queue = queue.Queue()

    # Shared thread pools for processing
    self.preprocess_pool = ThreadPoolExecutor(max_workers=1)
    self.detection_pool = ThreadPoolExecutor(max_workers=4)

    # Start background workers for each processing step
    for _ in range(4):
      self.preprocess_pool.submit(self._preprocess_worker)
      self.detection_pool.submit(self._detection_worker)

    # # Select all existing cameras in database 
    # with self.db as conn:
    #   cursor = conn.execute("SELECT CameraId, ip_address FROM Camera;")
    #   rows = cursor.fetchall()

    # Select all existing cameras
    cursor = self.db.cursor()
    cursor.execute("SELECT CameraId, ip_address FROM Camera;")
    rows = cursor.fetchall()
    cursor.close()

    # Start detection on all cameras and add them to the camera pool
    for camera_id, ip_address in rows:
      self.add_new_camera(camera_id, ip_address, True) 

    self._initialized = True

  def _preprocess_worker(self):
    from threads.preprocessor import preprocess
    models = [
      ObjectDetectionModel("yolo11n.pt", target_class_list, 0.3),
      ObjectDetectionModel("yolov8n.pt", target_class_list, 0.3),
      ObjectDetectionModel("yolov8m.pt", target_class_list, 0.3),
    ]
    pose_model = PoseDetectionModel("yolov8n-pose.pt", 0.80, 0.4)
    classif_model = ImageClassificationModel("yolov8n-cls.pt")

    while True:
      try:
        item = self.preprocess_queue.get(timeout=2)
        if item is SENTINEL:
          break

        camera, frame = item
        processed_frame = preprocess(camera, frame, models, pose_model, classif_model)
        self.detection_queue.put((camera, processed_frame))
      except queue.Empty:
        continue

  def _detection_worker(self):
    from threads.detector import detection
    while True:
      try:
        item = self.detection_queue.get(timeout=2)
        if item is SENTINEL:
          break

        camera, processed_frame = item
        detection(camera, processed_frame)
      except queue.Empty:
        continue

  def shutdown_all_cameras(self):
    """
    Gracefully shuts down all active cameras in the camera pool.
    Ensures that all camera and worker threads are properly terminated.
    """

    # Stop all camera threads.
    for camera_id, camera_info in self.camera_pool.items():
      camera = camera_info.get("camera")
      if camera:
        camera.running.clear()

      threads = camera_info.get("threads", {})
      for thread_name, thread in threads.items():
        thread.join(timeout=2)
        print(f"[INFO] Thread '{thread_name}' for camera {camera_id} joined.")

    self.camera_pool.clear()

    # Stop worker threads via sentinel
    for _ in range(self.preprocess_pool._max_workers):
      self.preprocess_queue.put(SENTINEL)
    for _ in range(self.detection_pool._max_workers):
      self.detection_queue.put(SENTINEL)

    # Shutdown thread pools
    self.preprocess_pool.shutdown(wait=True)
    self.detection_pool.shutdown(wait=True)

    print("[INFO] All worker and camera threads shut down successfully.")

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
    from threads.preprocessor import preprocess
    from threads.detector import detection
    from threads.saver import image_saver
    from shared.camera import Camera

    try:
      camera = Camera(camera_id, ip_address, channel, False, self)

      # Start all threads for detection
      read_thread = threading.Thread(target=read_frames, args=(camera,))
      save_thread = threading.Thread(target=image_saver, args=(camera,))


      read_thread.start()
      save_thread.start()

      self.camera_pool[camera_id] = {
        "camera": camera,
        "threads": {
          "read": read_thread,
          "save": save_thread,
        },
      }

      print(f"[INFO] Camera {camera_id} added.")
      return True

    except Exception:
      return False
