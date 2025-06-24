from ultralytics import YOLO
import os, uuid, math, queue, threading, time, json
import cv2 as cv
from datetime import datetime
import numpy as np
from deepface import DeepFace

cap = cv.VideoCapture(0)
cap.set(cv.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv.CAP_PROP_FRAME_HEIGHT, 720)
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
    global running
    while running:
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
                # Drop oldest to keep it fresh
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass
                frame_queue.put(frame)
        except Exception as e:
            print(f"Error putting frame into queue: {e}")

    cap.release()

def extract_face_from_nose(pose_points, frame):
    h, w = frame.shape[:2]
    
    nose = np.array(pose_points["nose"])
    l_eye = np.array(pose_points["left_eye"])
    r_eye = np.array(pose_points["right_eye"])
    l_ear = np.array(pose_points["left_ear"])
    r_ear = np.array(pose_points["right_ear"])
    
    # get the vertical distance of nose to eyes
    average_y_of_eyes = (l_eye[1] + r_eye[1]) // 2
    nose_to_eye_height = abs(nose[1] - average_y_of_eyes) * 3
    eye_center_y = average_y_of_eyes

    # add one unit (of nose_to_eye_height) above eye center, one below nose
    y1 = max(int(eye_center_y - nose_to_eye_height), 0)
    y2 = min(int(nose[1] + nose_to_eye_height), h)

    # horizontal distance of bbox based on ears
    x1 = max(int(min(l_ear[0], r_ear[0])), 0)
    x2 = min(int(max(l_ear[0], r_ear[0])), w)

    # check that bbox is valid
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Invalid bounding box dimensions.")

    return (x1, y1, x2, y2)

def get_dist_nose_to_box(pose_points, detected_food_drinks, track_id):

    # compute edge of food/drink bbox edges to nose point
    # get nose point
    nose = np.array(pose_points["nose"])

    # get food/ drinks bounding box coords
    food_drinks_bbox = detected_food_drinks[track_id][0]  # [x1, y1, x2, y2]
    x1, y1, x2, y2 = food_drinks_bbox

    # Clamp the nose to the bounding box (to get closest point on box edge)
    clamped_x = np.clip(nose[0], x1, x2)
    clamped_y = np.clip(nose[1], y1, y2)
    
    # Compute distance from nose to closest point on the bbox (euclidean distance formula)
    return np.linalg.norm(nose - np.array([clamped_x, clamped_y]))



def detection(model, pose_model, target_classes_id, conf_threshold):
    global running
    # flagged_foodbev = []

    while running:
        try:
            frame = frame_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        frame_copy = frame.copy()

        result = model.track(frame, persist=True, classes=target_classes_id, conf=conf_threshold, iou=0.4)

        boxes = result[0].boxes

        detected_food_drinks = {}
        
        # only process if there are at least 1 food/ drink detected
        if len(boxes) >= 1: 

            # object detection pipeline
            for box in boxes:
                track_id = int(box.id) if box.id is not None else None
                cls_id = int(box.cls.cpu())
                confidence = float(box.conf.cpu())
                coords = box.xyxy[0].cpu().numpy()
                
                x1, y1, x2, y2 = map(int, coords)

                if cls_id in food_beverage_class_list and track_id is not None:
                    detected_food_drinks[track_id] = [coords, ((coords[0] + coords[2]) // 2, (coords[1] + coords[3]) // 2)]
                    cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv.putText(frame_copy, f"id: {track_id}, conf: {confidence}", (x1 + 10, y1), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)


            pose_results = pose_model.track(frame, persist=True, conf=0.5, iou=0.4)[0]
            # pose_frame = pose_results.plot() # to see keypoints of pose
            keypoints = pose_results.keypoints.xy if pose_results.keypoints else []

            pose_points = []
            # only process if theres both faces and food/beverages in frame
            if detected_food_drinks and (keypoints is not None):
                # save landmarks for each person
                for person in keypoints:
                    try:
                        person_lm = person.cpu().numpy()
                        pose_points.append({
                            "nose": person_lm[0],
                            "left_wrist": person_lm[9],
                            "right_wrist": person_lm[10],
                            "left_ear": person_lm[3],
                            "right_ear": person_lm[4],
                            "left_eye": person_lm[1],
                            "right_eye": person_lm[2],
                        })
                    except Exception:
                        continue

            # only person and food/ drinks are found
            if pose_points and detected_food_drinks:
                for p in pose_points:
                    for track_id in detected_food_drinks:
                        #if track_id not in flagged_foodbev:

                            dist_nose_to_box = get_dist_nose_to_box(p, detected_food_drinks, track_id)

                            dist = min(
                                dist_nose_to_box,
                                np.linalg.norm(p["left_wrist"] - detected_food_drinks[track_id][1]),
                                np.linalg.norm(p["right_wrist"] - detected_food_drinks[track_id][1])
                            )
                            
                            DRINKING_THRESHOLD = 50
                            OWNING_THRESHOLD = 100
                            if dist <= OWNING_THRESHOLD or dist_nose_to_box <= DRINKING_THRESHOLD:
                                cv.putText(frame_copy, "NEAR DRINK", (int(p["nose"][0]), int(p["nose"][1]-10)), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                                try:
                                    face_bbox = extract_face_from_nose(p, frame)
                                    x1, y1, x2, y2 = map(int, face_bbox)
                                    face_crop = safe_crop(frame, x1, y1, x2, y2, padding=30)
                                    cv.imshow("face", face_crop)
                                    
                                except ValueError:
                                    continue
                                
                                if face_crop is not None and face_crop.size > 0:

                                    try:
                                        query_embedding = DeepFace.represent(img_path=face_crop, model_name="Facenet", max_faces=1, enforce_detection=False)[0]["embedding"]

                                        # find match in database
                                        closest_dist = float('inf')
                                        closest_match_id = None
                                        for fid, ref_embedding in embeddings_db.items():
                                            distance_vector = np.square(query_embedding - ref_embedding)
                                            distance = np.sqrt(distance_vector.sum())

                                            if distance < closest_dist:
                                                closest_dist = distance
                                                closest_match_id = fid

                                        # match found
                                        if closest_dist < 7.5:

                                            current_date = datetime.now().strftime("%Y%m%d")

                                            if incompliance_date_map[closest_match_id] != current_date:

                                                # update last incompliance date (temp: also add embeddings in in-memory dictionary)
                                                incompliance_date_map[closest_match_id] = current_date
                                                embeddings_db[closest_match_id] = np.array(query_embedding)

                                                # get the existing uuid of face and save incompliance img into folder
                                                save_img(face_crop, closest_match_id, current_date, "faces")
                                                save_img(frame_copy, closest_match_id, current_date, "incompliances")

                                                print(f"[ACTION] Similar face found 🟢: {closest_match_id}. Saving incompliance snapshot and updated last incompliance date ✅")
                                                
                                            # incompliance on the same date
                                            else:
                                                print("🟣🟣🟣🟣")
                                        # no match
                                        else:

                                            # generate new uuid for face/person
                                            new_uuid = str(uuid.uuid4())

                                            current_date = datetime.now().strftime("%Y%m%d")

                                            os.makedirs(os.path.join(WORKING_DIR, "incompliances", new_uuid), exist_ok=True)
                                            # save cropped face area save it for matching next time
                                            os.makedirs(os.path.join(WORKING_DIR ,"faces", new_uuid), exist_ok=True)

                                            # update last incompliance date and save incompliance img
                                            incompliance_date_map[new_uuid] = current_date
                                            embeddings_db[new_uuid] = np.array(query_embedding)
                
                                            save_img(face_crop, new_uuid, current_date, "faces")
                                            save_img(frame_copy, new_uuid, current_date, "incompliances")

                                            print(f"[NEW] No face found 🟡. Saving incompliance snapshot and updated last incompliance date ✅")

                                    except Exception as e:
                                        continue
                            
                            
        # display
        # annotated_frame = cv.resize(annotated_frame, (annotated_frame.shape[1] // 2, annotated_frame.shape[0] // 2))
        cv.imshow('YOLO Webcam Detection', frame_copy)

        if cv.waitKey(1) & 0xFF == ord('q'):
            running = False
            break

# create folders for faces and incompliances.
WORKING_DIR = r"C:\Users\framn\Downloads\pythonPrac\ITP" # change working directory here
os.makedirs(os.path.join(WORKING_DIR, "faces"), exist_ok=True)
os.makedirs(os.path.join(WORKING_DIR, "incompliances"), exist_ok=True)
os.makedirs(os.path.join(WORKING_DIR, "yolo_models"), exist_ok=True)

# load yolo model and target classes
model = YOLO(os.path.join(WORKING_DIR, "yolo_models", "yolo11s.pt"))
pose_model = YOLO("yolo_models/yolov8n-pose.pt")
food_beverage_class_list = [39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]
print(f"[START] Loaded YOLO model")


# temporarily using json file to store embeddings to mimick database
incompliance_date_map = {} # { "uuid": YYYYMMDD }
embeddings_db = {}  # { "uuid": embedding_vector }

with open('incompliances.json', 'r') as file:
  db = json.load(file)

for face_id, em in db['embeddings'].items():
  embeddings_db[face_id] = np.array(em)

for face_id, date in db['dates'].items():
  incompliance_date_map[face_id] = date


print(f"[START] Set up completed")

# Start threads
read_thread = threading.Thread(target=read_frames)
inference_thread = threading.Thread(target=detection, args=(model, pose_model, food_beverage_class_list, 0.3))
save_thread = threading.Thread(target=image_saver, daemon=True)

read_thread.start()
inference_thread.start()
save_thread.start()

try:
    while running:
        time.sleep(1)
except KeyboardInterrupt:
    running = False

read_thread.join()
inference_thread.join()

cap.release()
cv.destroyAllWindows()

print(f"[END]")
