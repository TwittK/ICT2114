import cv2 as cv
import os
import asyncio

async def save_img(frame_or_face, uuid_str, timestamp, faces_or_incompliance):
    
    folder = os.path.join("web", "static", faces_or_incompliance, uuid_str)
    os.makedirs(folder, exist_ok=True)

    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join(folder, filename)

    await asyncio.to_thread(cv.imwrite, filepath, frame_or_face)
    print(f"Saved {folder}\{filename} asynchronously")