# shared/camera_manager.py
import threading, sqlite3

target_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]

# [39, 40, 41]
# just the drinks from coco dataset
# bread: 31, chips: 55, chocolate: 56, cookies: 67, desserts: 77, french fries: 86, hamburger: 100, ice-cream: 108, pastry: 156, waffles: 231
# food_class_list = [31, 55, 56, 67, 77, 86, 100, 108, 156, 231]


class CameraManager:
  _instance = None

  # Singleton
  def __new__(cls, db_path):
    if cls._instance is None:
      cls._instance = super(CameraManager, cls).__new__(cls)
      cls._instance._initialized = False
    return cls._instance
  
  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      raise RuntimeError("CameraManager has not been initialized yet.")
    return cls._instance

  def __init__(self, db_path):

    if self._initialized: # Singleton
      return 
    
    self.camera_pool = {}
    self.db = sqlite3.connect(db_path)

    # Select all existing cameras in database 
    with self.db as conn:
      cursor = conn.execute("SELECT CameraId, ip_address FROM Camera;")
      rows = cursor.fetchall()

    # Start detection on all cameras and add them to the camera pool
    for camera_id, ip_address in rows:
      # self.add_new_camera(camera_id, ip_address, "101", False)
      self.add_new_camera(camera_id, ip_address, "101", use_ip_camera=False, use_image_folder=True, image_folder="test_images/far", distance_label="far")

    self._initialized = True
  
  def shutdown_all_cameras(self):
    for camera_id, camera_info in self.camera_pool.items():
      camera = camera_info.get("camera")
      if camera:
        camera.running.clear()

      threads = camera_info.get("threads", {})
      for thread_name, thread in threads.items():
        thread.join(timeout=2)
        print(f"[INFO] Thread '{thread_name}' for camera {camera_id} joined.")

  def remove_camera(self, camera_id):
    if camera_id not in self.camera_pool:
      print(f"[ERROR] Camera {camera_id} is not running.")
      return False
  
    camera = self.camera_pool[camera_id]["camera"]
    if camera:
      camera.running.clear()

    camera_threads = self.camera_pool[camera_id]["threads"]
    for thread_name, thread in camera_threads.items():
      thread.join(timeout=2)
      print(f"[INFO] Thread '{thread_name}' for camera {camera_id} joined.")

    del self.camera_pool[camera_id]
    return True

  def add_new_camera(self, camera_id, ip_address, channel, use_ip_camera, use_image_folder=False, image_folder=None, distance_label=None):
    from threads.reader import read_frames
    from threads.preprocessor import preprocess
    from threads.detector import detection
    from threads.saver import image_saver
    from shared.camera import Camera

    try:
      camera = Camera(camera_id, ip_address, channel, use_ip_camera, self,
                      use_image_folder=use_image_folder, image_folder=image_folder, distance_label=distance_label)

      # Start all threads for detection
      read_thread = threading.Thread(target=read_frames, args=(camera,))
      preprocess_thread = threading.Thread(target=preprocess, args=(camera, target_class_list, 0.3))
      detection_thread = threading.Thread(target=detection, args=(camera,))
      save_thread = threading.Thread(target=image_saver, args=(camera,))


      read_thread.start()
      preprocess_thread.start()
      detection_thread.start()
      save_thread.start()

      self.camera_pool[camera_id] = {
        "camera": camera,
        "threads": {
          "read": read_thread,
          "detection": detection_thread,
          "save": save_thread,
          "preprocess": preprocess_thread
        },
      }

      print(f"[INFO] Camera {camera_id} added.")
      return True

    except Exception:
      return False
