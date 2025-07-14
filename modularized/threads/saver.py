import cv2 as cv
import os
import threads.camera as Camera

def save_img(context: Camera, frame, uuid_str, timestamp):

    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join("web", "static", "incompliances", uuid_str, filename)
    context.save_queue.put((filepath, frame))

# Save images to disk
def image_saver(context: Camera):

    while context.running:

        item = context.save_queue.get()
        if item is None:
            break

        filepath, frame = item
        
        cv.imwrite(filepath, frame)
        print(f"Saved in {filepath}")
        context.save_queue.task_done()