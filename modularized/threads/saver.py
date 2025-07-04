import cv2 as cv
import os
from shared.state import save_queue, running

def save_img(frame_or_face, uuid_str, timestamp, faces_or_incompliance):
    # global save_queue
    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join("static", faces_or_incompliance, uuid_str, filename)
    save_queue.put((filepath, frame_or_face))

# Save images to disk
def image_saver():
    # global running, save_queue
    while running:
        filepath, image = save_queue.get()
        if filepath is None:
            break
        cv.imwrite(filepath, image)
        print(f"Saved in {filepath}")
        save_queue.task_done()