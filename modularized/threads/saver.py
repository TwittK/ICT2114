import cv2 as cv
import os, queue, threading

class Saver:
    
    _instance = None

    # Singleton
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Saver, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            raise RuntimeError("Saver has not been initialized yet.")
        return cls._instance

    def __init__(self):
        if self._initialized: # Singleton
            return 
        
        self.save_queue = queue.Queue()
        self.thread = threading.Thread(target=self.image_saver, name=f"Save Thread", daemon=True)
        self.running = threading.Event()
        self.running.set()
        self.thread.start()
        print("[INFO] Save thread started.")


    def save_img(self, frame, uuid_str, timestamp):
        """
        Queue a frame to be saved as an image on disk.

        This function constructs a file path, and places the frame and
        path into a queue for saving.

        Parameters:
            frame (np.ndarray): The image frame to be saved.
            uuid_str (str): Unique identifier for the person.
            timestamp (str): Image timestamp. (YYYY-MM-DD)
        """

        filename = f"Person_{uuid_str}_{timestamp}.jpg"
        filepath = os.path.join("web", "static", "incompliances", uuid_str, filename)
        self.save_queue.put((filepath, frame))

    # Save images to disk
    def image_saver(self):
        """
        Continuously processes the save queue and writes images to disk.

        Pulls file path and frame from the `save_queue`, and saves each frame to the corresponding 
        path. Exits when a `None` item is received.
        """
        while self.running.is_set():
            
            try:
                item = self.save_queue.get(timeout=1)
            except queue.Empty:
                continue

            if item is None:
                break

            filepath, frame = item
            
            cv.imwrite(filepath, frame)
            print(f"Saved in {filepath}")
            self.save_queue.task_done()
    
    def stop(self):
        self.save_queue.put(None)
        self.running.clear()
        self.thread.join(timeout=2)
        print(f"[INFO] Saver thread stopped.")