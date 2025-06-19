from ultralytics import YOLO
import os, uuid, math, queue, threading, time, json
import cv2 as cv
from datetime import datetime
import numpy as np
from deepface import DeepFace

cap = cv.VideoCapture(0)
if not cap.isOpened():
    print("[ERROR] Cannot open camera")
    exit()
frame_queue = queue.Queue(maxsize=10)
save_queue = queue.Queue(maxsize=10)
running = True

def save_img(frame_or_face, uuid_str, timestamp, faces_or_incompliance):
    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join(WORKING_DIR, faces_or_incompliance, uuid_str, filename)
    save_queue.put((filepath, frame_or_face))
    
def image_saver():
    while True:
        filepath, image = save_queue.get()
        if filepath is None:
            break
        cv.imwrite(filepath, image)
        save_queue.task_done()

def safe_crop(img, x1, y1, x2, y2, padding=0):
    h, w, _ = img.shape
    x1 = max(x1 - padding, 0)
    y1 = max(y1 - padding, 0)
    x2 = min(x2 + padding, w)
    y2 = min(y2 + padding, h)
    return img[y1:y2, x1:x2]

def find_near_or_overlapping_boxes(bev_coords, face_coords, threshold=50):

    matches = {i: [] for i in bev_coords}

    for bev_track_id, box1 in bev_coords.items():
        x1_a, y1_a, x2_a, y2_a = box1[0]

        for face_track_id, box2 in face_coords.items():
            x1_b, y1_b, x2_b, y2_b = box2[0]

            """
            checks if boxes are entirely to the left/right of each other
            x2_a < x1_b: box a is fully to the left of box b
            x2_b < x1_a: box a is fully to the right of box b

            checks if boxes are entirely above/below each other
            y2_a < y1_b: box a is fully above box b
            y2_b < y1_a: box a is fully below box b
            """
            is_separated = x2_a < x1_b or x2_b < x1_a or y2_a < y1_b or y2_b < y1_a

            # check near edges
            horiz_gap = max(0, max(x1_b - x2_a, x1_a - x2_b))
            verti_gap = max(0, max(y1_b - y2_a, y1_a - y2_b))
            near = horiz_gap <= threshold and verti_gap <= threshold

            if (is_separated == False) or near:
                matches[bev_track_id].append(face_track_id)

    return matches # returns list of food/bev to face mapping {food/bev track id : [track id of faces reasonably close to it]}

def euclidean_distance(center1, center2):
    return math.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)

def find_nearest_faces(filtered_near_faces, bev_coords, face_coords):
    # filtered_matches: {bev1: [list of all near faces that are real], bev2: [list of all near faces that are real], ...}
    # function takes filtered_matches and finds the closest face for each food/ beverage using euclidean distance.
    
    nearest_pairs = []
    
    for bev, faces in filtered_near_faces.items():
        min_dist = float('inf')
        nearest_face = None
        
        for face in faces:
            dist = euclidean_distance(bev_coords[bev][1], face_coords[face][1])
            if dist < min_dist:
                min_dist = dist
                nearest_face = face
        
        nearest_pairs.append((bev, nearest_face))
    
    return nearest_pairs # function returns a list of tuples: [(food/ beverage detected, its closest face), (food/ beverage detected, its closest face), ...]

def read_frames():
    global running

    while running:
        ret, frame = cap.read()

        if not ret or frame is None or frame.size == 0:
            print("[ERROR] Dropped a corrupted or empty frame.")
            continue

        try:
            if not frame_queue.full():
                frame_queue.put(frame)
            else:
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass
                frame_queue.put(frame)
        except Exception as e:
            print(f"Error putting frame into queue: {e}")

    cap.release()

def detection(model, target_classes_id, conf_threshold):
    global running
    flagged_foodbev = [] # store a list of food/beverage ids so that once it has been matched to an owner, it can't be matched to another person again

    while running:
        try:
            frame = frame_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        result = model.track(frame, persist=True, classes=target_classes_id, conf=conf_threshold)
        annotated_frame = result[0].plot()
        boxes = result[0].boxes

        boxes_beverage = {}
        boxes_face = {}

        # only process if there are at least 2 detected objects
        if len(boxes) >= 2: 

            # prepare detected object's coords and center
            for box in boxes:
                track_id = int(box.id) if box.id is not None else None
                cls_id = int(box.cls.cpu())
                coords = box.xyxy[0].cpu().numpy()

                # food/ beverages
                if cls_id in food_beverage_class_list and track_id is not None:
                    boxes_beverage[track_id] = [coords, ((coords[0] + coords[2]) // 2, (coords[1] + coords[3]) // 2)]
                # person
                elif cls_id in human_class_list and track_id is not None:
                    boxes_face[track_id] = [coords, ((coords[0] + coords[2]) // 2, (coords[1] + coords[3]) // 2)]

            # only process if theres both faces and food/beverages in frame
            if boxes_beverage and boxes_face:
                
                # ensure only faces that are reasonably near to food/bev are considered (will not consider any faces that are far away for anti spoof check)
                max_detection_dist = 50
                near_faces = find_near_or_overlapping_boxes(boxes_beverage, boxes_face, threshold=max_detection_dist)

                # find nearest face using euclidean distance
                filtered_nearest_pairs = find_nearest_faces(near_faces, boxes_beverage, boxes_face) 

                # (1 food/bev map to one person, 1 food/bev can map to only 1 face, 1 face can map to 1 or more food/bev)
                for bev_idx, nearest_face_idx in filtered_nearest_pairs:
                    if bev_idx not in flagged_foodbev:
                        try:
                            nearest_face = boxes_face[nearest_face_idx]

                            if nearest_face:
                                x1_face, y1_face, x2_face, y2_face = map(int, nearest_face[0])
                                cv.putText(annotated_frame, "FLAGGED", (x1_face + 10, y1_face + 20), cv.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2, cv.LINE_AA, False)


                                face_only = safe_crop(frame, x1_face, y1_face, x2_face, y2_face)
                                face_only_rgb = cv.cvtColor(face_only, cv.COLOR_BGR2RGB)
                                
                                # compare nearest face and see if there is a match
                                try:
                                    # prepare embedding vector of closest real face 
                                    query_embedding = DeepFace.represent(img_path=face_only_rgb, model_name="OpenFace")[0]["embedding"]
                                    lowest_dist = math.inf

                                    # perform facial recognition on each face with faces of past incompliances
                                    for embed_uuid, ref_embedding in embeddings_db.items():

                                        # calculate similarity score by using embedding vectors
                                        cosine_sim = query_embedding @ ref_embedding
                                        dist = 1 - cosine_sim

                                        # get face that looks the most similar
                                        if dist < lowest_dist:
                                            lowest_dist = dist

                                    # found a match
                                    if lowest_dist <= 0.45:
                                        flagged_foodbev.append(bev_idx) # save track id of bottle
                                        current_date = datetime.now().strftime("%Y%m%d")
                                        
                                        print(current_date)
                                        # new incompliance with same person on a different date
                                        if incompliance_date_map[embed_uuid] != current_date:

                                            # update last incompliance date (temp: also add embeddings in in-memory dictionary)
                                            incompliance_date_map[embed_uuid] = current_date
                                            embeddings_db[embed_uuid] = np.array(query_embedding)

                                            # get the existing uuid of face and save incompliance img into folder
                                            save_img(face_only, embed_uuid, current_date, "faces")
                                            save_img(annotated_frame, embed_uuid, current_date, "incompliances")

                                            print(f"[ACTION] Similar face found 🟢: {embed_uuid}. Saving incompliance snapshot and updated last incompliance date ✅")

                                        # incompliance on the same date
                                        else:
                                            print("[LOG] 🟣 Similar face found but already have incompliance on the same day.")
                                        
                                    # no match
                                    else:
                                        flagged_foodbev.append(bev_idx) # save track id of bottle

                                        # generate new uuid for face/person
                                        new_uuid = str(uuid.uuid4())

                                        current_date = datetime.now().strftime("%Y%m%d")

                                        os.makedirs(os.path.join(WORKING_DIR, "incompliances", new_uuid), exist_ok=True)
                                        # save cropped face area save it for matching next time
                                        os.makedirs(os.path.join(WORKING_DIR ,"faces", new_uuid), exist_ok=True)

                                        # update last incompliance date and save incompliance img
                                        incompliance_date_map[new_uuid] = current_date
                                        embeddings_db[new_uuid] = np.array(query_embedding)
            
                                        save_img(face_only, new_uuid, current_date, "faces")
                                        save_img(annotated_frame, new_uuid, current_date, "incompliances")

                                        print(f"[ACTION] No face found 🟡. Saving incompliance snapshot and updated last incompliance date ✅")
                                        
                                except ValueError:
                                    pass 
                            else:
                                print("[LOG] No nearest face 🔵")

                        except KeyError:
                            pass 

        # display
        # annotated_frame = cv.resize(annotated_frame, (annotated_frame.shape[1] // 2, annotated_frame.shape[0] // 2))
        cv.imshow('YOLO Webcam Detection', annotated_frame)

        if cv.waitKey(1) & 0xFF == ord('q'):
            running = False
            break

# create folders for faces and incompliances.
WORKING_DIR = r"" # change working directory here

os.makedirs(os.path.join(WORKING_DIR, "faces"), exist_ok=True)
os.makedirs(os.path.join(WORKING_DIR, "incompliances"), exist_ok=True)
os.makedirs(os.path.join(WORKING_DIR, "yolo_models"), exist_ok=True)

model = YOLO(os.path.join(WORKING_DIR, "yolo_models", "yolo11s.pt"))
print(f"[START] Loaded YOLO model")

food_beverage_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]
human_class_list = [0]

incompliance_date_map = {} # { "uuid": YYYYMMDD }
embeddings_db = {}  # { "uuid": embedding_vector }

# collate embeddings of all exisiting images upon start and store a dict of when the last incompliance occured for each face
FACES_DIR = os.path.join(WORKING_DIR, "faces")
for folder in os.listdir(os.path.join(WORKING_DIR, "faces")):

    folder_dir = os.path.join(FACES_DIR, folder)

    for file in os.listdir(folder_dir):

        # prepare file paths in correct format
        img_path = os.path.join(folder_dir, file)
        # remove file extension
        filename_wo_ext = os.path.splitext(file)[0]
        # extract uuid of face
        uuid_part = filename_wo_ext.split("_")[1]

        # calculate embeddings of face image and add them to a dict
        embedding = DeepFace.represent(img_path=img_path, model_name="OpenFace")[0]["embedding"]
        embeddings_db[uuid_part] = np.array(embedding)
        
        # extract incompliance date from filename
        last_incompliance_date = str(filename_wo_ext).split("_")[2]
        # update history of the latest incompliance dates of each face
        if uuid_part not in incompliance_date_map or last_incompliance_date > incompliance_date_map[uuid_part]:
            incompliance_date_map[uuid_part] = last_incompliance_date

print(incompliance_date_map)
print(f"[START] Set up completed")

# Start threads
read_thread = threading.Thread(target=read_frames)
inference_thread = threading.Thread(
    target=detection, args=(model, food_beverage_class_list + human_class_list, 0.3)
)

read_thread.start()
inference_thread.start()
threading.Thread(target=image_saver, daemon=True).start()

try:
    while running:
        time.sleep(1)
except KeyboardInterrupt:
    running = False

read_thread.join()
inference_thread.join()

cv.destroyAllWindows()
print(f"[END]")
