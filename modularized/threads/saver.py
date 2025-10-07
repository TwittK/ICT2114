import cv2 as cv
import os, queue
import shared.camera as Camera

def save_img(context: Camera, frame, uuid_str, timestamp):
    """
    Queue a frame to be saved as an image on disk.

    This function constructs a file path, and places the frame and
    path into a queue for saving.

    Parameters:
        context (Camera): Camera containing the save queue.
        frame (np.ndarray): The image frame to be saved.
        uuid_str (str): Unique identifier for the person.
        timestamp (str): Image timestamp. (YYYY-MM-DD)
    """

    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join("web", "static", "incompliances", uuid_str, filename)
    context.save_queue.put((filepath, frame))

# Save images to disk
def image_saver(context: Camera):
    """
    Continuously processes the save queue and writes images to disk.

    Pulls file path and frame from the `save_queue`, and saves each frame to the corresponding 
    path. Exits when a `None` item is received.

    Parameters:
        context (Camera): Camera context that contains the save queue and running flag.
    """
    while context.running.is_set():
        
        try:
            item = context.save_queue.get(timeout=1)
        except queue.Empty:
            continue

        if item is None:
            break

        filepath, frame = item
        
        cv.imwrite(filepath, frame)
        print(f"Saved in {filepath}")
        context.save_queue.task_done()