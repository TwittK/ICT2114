# shared/detection_manager.py
import threading
from threads.preprocessor import DetectionWorker


class DetectionManager:
  """
  Singleton class that manages multiple DetectionWorker threads to process incoming frames.

  Distsributes frames among a fixed number of workers (according to number of available GPUs, defined in .env file)
  using round-robin scheduling.
  """

  _instance = None

  # Singleton
  def __new__(cls, num_workers):
    if cls._instance is None:
      cls._instance = super(DetectionManager, cls).__new__(cls)
      cls._instance._initialized = False
    return cls._instance
  
  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      raise RuntimeError("DetectionManager has not been initialized yet.")
    return cls._instance

  def __init__(self, num_workers):
    """
    Initializes the DetectionManager with a specified number of DetectionWorker threads. 1 Worker = 1 YOLO Detection Queue = 1 GPU

    Parameters:
      num_workers (int): The number of workers to create.
    """
    if self._initialized: # Singleton
      return 
    
    self.workers = []
    self.next_worker_index = 0 # For round-robin selection
    self.lock = threading.Lock() 

    for i in range(int(num_workers)):
      worker = DetectionWorker(i)
      self.workers.append(worker)

  
  def submit(self, frame, camera):
    """
    Submit a frame and its associated camera to a worker for processing.

    This method uses round-robin scheduling to distribute incoming
    frames across all detection workers.

    Parameters:
      frame: The frame data to be processed (e.g., an image or video frame).
      camera: Metadata or identifier associated with the camera that provided the frame.
    """
    with self.lock:

      # Set the current worker
      worker = self.workers[self.next_worker_index]

      # Increment to the next worker, modulus to cap it at the max num of workers
      self.next_worker_index = (self.next_worker_index + 1) % len(self.workers)
    worker.submit(frame, camera)

  def stop_all(self):
    """
    Stops all DetectionWorker threads managed by this DetectionManager.
    """
    for worker in self.workers:
      worker.stop()