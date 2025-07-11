import cv2 as cv
import os
import shared.state as shared_state

def save_img(frame_or_face, uuid_str, timestamp, faces_or_incompliance):
    # global save_queue
    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join("web", "static", faces_or_incompliance, uuid_str, filename)
    shared_state.save_queue.put((filepath, frame_or_face))

# Save images to disk
def image_saver():
    # global running, save_queue
    while shared_state.running:

        item = shared_state.save_queue.get()
        if item is None:
            break

        filepath, image = item
        
        cv.imwrite(filepath, image)
        print(f"Saved in {filepath}")
        shared_state.save_queue.task_done()