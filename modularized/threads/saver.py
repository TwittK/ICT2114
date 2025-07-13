import cv2 as cv
import os
import shared.state as shared_state

def save_img(frame, uuid_str, timestamp):
    # global save_queue
    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join("web", "static", "incompliances", uuid_str, filename)
    shared_state.save_queue.put((filepath, frame))

# Save images to disk
def image_saver():
    # global running, save_queue
    while shared_state.running:

        item = shared_state.save_queue.get()
        if item is None:
            break

        filepath, frame = item
        
        cv.imwrite(filepath, frame)
        print(f"Saved in {filepath}")
        shared_state.save_queue.task_done()