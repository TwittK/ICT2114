# shared/detection_manager.py
import threading
from threads.preprocessor import DetectionWorker


class DetectionManager:
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

    if self._initialized: # Singleton
      return 
    
    self.workers = []
    self.next_worker_index = 0 # For round-robin selection
    self.lock = threading.Lock() 

    for i in range(int(num_workers)):
      worker = DetectionWorker(i)
      self.workers.append(worker)

  
  def submit(self, frame, camera):
    """Distribute frames round-robin to worker queues."""
    with self.lock:

      # Set the current worker
      worker = self.workers[self.next_worker_index]

      # Increment to the next worker, modulus to cap it at the max num of workers
      self.next_worker_index = (self.next_worker_index + 1) % len(self.workers)
    worker.submit(frame, camera)

  def stop_all(self):
    for worker in self.workers:
      worker.stop()