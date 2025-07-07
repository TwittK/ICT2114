from flask import Flask, Response, request, jsonify, render_template
import cv2, threading, time, queue, sys, os
from flask import Flask, Response, render_template_string
import cv2 as cv
from ultralytics import YOLO
from datetime import datetime
import numpy as np
from deepface import DeepFace
import sqlite3, sqlite_vec
from sqlite_vec import serialize_float32


frame_queue = queue.Queue(maxsize=10)
save_queue = queue.Queue(maxsize=10)
process_queue = queue.Queue(maxsize=10)
display_queue = queue.Queue(maxsize=10)
running = True

detected_incompliance_lock = threading.Lock()
pose_points_lock = threading.Lock()
flagged_foodbev_lock = threading.Lock()

# Create folders for faces and incompliances
os.makedirs(os.path.join("static", "faces"), exist_ok=True)
os.makedirs(os.path.join("static", "incompliances"), exist_ok=True)
os.makedirs("yolo_models", exist_ok=True)

# Load yolo models for object detection and pose, as well as target classes
# food_model = YOLO(os.path.join("yolo_models", "best.pt"))
# food_class_list = [0]

drink_model = YOLO(os.path.join("yolo_models", "yolo11m.pt"))
beverage_class_list = [39, 40, 41] # just the drinks from coco dataset

pose_model = YOLO(os.path.join("yolo_models", "yolov8n-pose.pt"))

# Uncomment for yolov8x testing, test either food_class_list or beverage_class_list at a time.
food_model = YOLO(os.path.join("yolo_models", "yolov8x.pt")) # use for yolov8x testing
#bread: 31, chips: 55, chocolate: 56, cookies: 67, desserts: 77, french fries: 86, hamburger: 100, ice-cream: 108, pastry: 156, waffles: 231
food_class_list = [31, 55, 56, 67, 77, 86, 100, 108, 156, 231]
# #beer: 19, beverages: 23, coffee: 59, juice: 111, kymyz-kymyran: 119, milk: 134, soda: 203 spirits: 208, tea: 221, water: 234, wine: 236
# # beverage_class_list = [19, 23, 59, 111, 119, 134, 203, 208, 221, 234, 236] 


flagged_foodbev = [] # Format: [track ids]
pose_points = []
detected_incompliance = {} # Format: { track_id, [coords(List Of 4 Values), center(Tuple Of 2 Values), confidence(Float), classId(Integer)] }

# Track wrist proximity times per person
wrist_proximity_history = {}  # Format: {track_id: [timestamps]}
print(f"[START] Set up completed")

# Constants
DRINKING_THRESHOLD = 50 # Distance thresholds
OWNING_THRESHOLD = 200
REQUIRED_DURATION = 2.0  # seconds
REQUIRED_COUNT = 3      # number of detections in that duration
FACE_DISTANCE_THRESHOLD = 10

app = Flask(__name__)

def safe_crop(img, x1, y1, x2, y2, padding=0):
    h, w, _ = img.shape
    x1 = max(x1 - padding, 0)
    y1 = max(y1 - padding, 0)
    x2 = min(x2 + padding, w)
    y2 = min(y2 + padding, h)
    return img[y1:y2, x1:x2]

# Estimates the facial area based on the nose, eyes and ears
def extract_face_from_nose(pose_points, frame):
    h, w = frame.shape[:2]
    
    nose = np.array(pose_points["nose"])
    l_eye = np.array(pose_points["left_eye"])
    r_eye = np.array(pose_points["right_eye"])
    l_ear = np.array(pose_points["left_ear"])
    r_ear = np.array(pose_points["right_ear"])
    
    # Get the vertical distance of nose to eyes
    average_y_of_eyes = (l_eye[1] + r_eye[1]) // 2
    nose_to_eye_height = abs(nose[1] - average_y_of_eyes) * 3
    eye_center_y = average_y_of_eyes

    # Add one unit (of nose_to_eye_height) above eye center, one below nose
    y1 = max(int(eye_center_y - nose_to_eye_height), 0)
    y2 = min(int(nose[1] + nose_to_eye_height) + 20, h)

    # Horizontal distance of bbox based on ears
    x1 = max(int(min(l_ear[0], r_ear[0])), r_eye[0] - 40)
    x2 = min(int(max(l_ear[0], r_ear[0])), l_eye[0] + 40)

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

def save_img(frame_or_face, uuid_str, timestamp, faces_or_incompliance):
    global save_queue
    filename = f"Person_{uuid_str}_{timestamp}.jpg"
    filepath = os.path.join("static", faces_or_incompliance, uuid_str, filename)
    save_queue.put((filepath, frame_or_face))

# Save images to disk
def image_saver():
    global running, save_queue
    while running:
        filepath, image = save_queue.get()
        if filepath is None:
            break
        cv.imwrite(filepath, image)
        print(f"Saved in {filepath}")
        save_queue.task_done()

# Read frames from camera
def read_frames():
    global running, cap, frame_queue

    cap = cv.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera")
        exit()

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
            print(f"Error putting frame into frame queue: {e}")

    cap.release()

# Display annotated frames on dashboard
def preprocess(drink_model, food_model, pose_model, target_classes_id_drink, target_classes_id_food, conf_threshold):
    global running
    global frame_queue, process_queue, display_queue
    global detected_incompliance_lock, pose_points_lock, flagged_foodbev_lock
    global flagged_foodbev, pose_points, detected_incompliance

    while running:
        try:
            frame = frame_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # perform image processing here
        frame_copy = frame.copy() # copy frame for drawing bounding boxes, ids and conf scores.

        # Drink detection
        result = drink_model.track(frame_copy, persist=True, classes=target_classes_id_drink, conf=conf_threshold, iou=0.4, verbose=False)
        drink_boxes = result[0].boxes
        
        # Food detection
        food_results = food_model.track(frame_copy, persist=True, classes=target_classes_id_food, conf=conf_threshold, iou=0.4, verbose=False)
        food_boxes = food_results[0].boxes


        with detected_incompliance_lock:
            detected_incompliance.clear()

        # only process if there are at least 1 food/ drink detected
        # if len(boxes) >= 1: 
        if (drink_boxes and len(drink_boxes) >= 1) or (food_boxes and len(food_boxes) >= 1):

            if datetime.now().strftime("%H:%M") == "00:00": # refresh flagged track ids daily
                with flagged_foodbev_lock:
                    flagged_foodbev.clear()

            # object detection pipeline
            with detected_incompliance_lock:
                # Process drinks
                for box in drink_boxes:
                    track_id = int(box.id) if box.id is not None else None
                    cls_id = int(box.cls.cpu())
                    confidence = float(box.conf.cpu())
                    coords = box.xyxy[0].cpu().numpy()
                    class_name = drink_model.names[cls_id]
                    print(f"[Drink] {class_name} (ID: {cls_id}) - {confidence:.2f}")
                    
                    x1, y1, x2, y2 = map(int, coords)

                    if track_id is not None:
                        detected_incompliance[track_id] = [coords, ((coords[0] + coords[2]) // 2, (coords[1] + coords[3]) // 2), confidence, cls_id]
                        cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv.putText(frame_copy, f"id: {track_id}, conf: {confidence:.2f}", (x1, y1 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                # Process food 
                for box in food_boxes:
                    track_id = int(box.id) if box.id is not None else None
                    cls_id = int(box.cls.cpu())
                    confidence = float(box.conf.cpu())
                    coords = box.xyxy[0].cpu().numpy()
                    class_name = food_model.names[cls_id]
                    print(f"[Food] {class_name} (ID: {cls_id}) - {confidence:.2f}")

                    x1, y1, x2, y2 = map(int, coords)

                    if track_id is not None:
                        detected_incompliance[track_id] = [coords, ((coords[0] + coords[2]) // 2, (coords[1] + coords[3]) // 2), confidence, cls_id]
                        cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv.putText(frame_copy, f"{class_name} id:{track_id} conf:{confidence:.2f}", (x1, y2 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            pose_results = pose_model.track(frame, persist=True, conf=0.5, iou=0.4, verbose=False)[0]
            keypoints = pose_results.keypoints.xy if pose_results.keypoints else []

            with pose_points_lock:
                pose_points.clear()

            with detected_incompliance_lock and pose_points_lock:
                # only process if theres both faces and food/beverages in frame
                if detected_incompliance and (keypoints is not None):
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
            
            # Put into process queue for the next step (mapping food/ drinks to faces)
            with detected_incompliance_lock and pose_points_lock:   
                if pose_points and detected_incompliance:    
                    try:
                        if not process_queue.full():
                            process_queue.put(frame)

                        else:
                            try:
                                process_queue.get_nowait()
                            except queue.Empty:
                                pass
                            process_queue.put(frame)

                    except Exception as e:
                        print(f"Error putting frame into process queue: {e}")

        # Put into queue to display frames in dashboard
        if not display_queue.full():
            display_queue.put(frame_copy)
        else:
            try:
                display_queue.get_nowait()
            except queue.Empty:
                pass
            display_queue.put(frame_copy)

# Associate detected food/ drinks to person
def detection():
    global running
    global save_queue, process_queue
    global detected_incompliance_lock, pose_points_lock, flagged_foodbev_lock
    global flagged_foodbev, pose_points, detected_incompliance
    global wrist_proximity_history

    # db = sqlite3.connect("database/test.sqlite")
    db = sqlite3.connect("users.sqlite")
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    while running:
        try:
            frame = process_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue
        
        # shallow copy for reading in this thread
        with detected_incompliance_lock, pose_points_lock:
            local_pose_points = list(pose_points)
            local_incompliance = dict(detected_incompliance)


        for p in local_pose_points:
            for track_id in local_incompliance:

                with flagged_foodbev_lock:
                    if track_id in flagged_foodbev:
                        continue

                food_drinks_bbox = local_incompliance[track_id][0] 
                x1, y1, x2, y2 = food_drinks_bbox

                try:
                    face_bbox = extract_face_from_nose(p, frame)
                    fx1, fy1, fx2, fy2 = map(int, face_bbox)

                except ValueError:
                    print("can't extract the face")
                    continue

                # if the top of food/ drink bbox is a percentage above the nose, ignore
                if (y1 < p["nose"][1] * 0.95):
                    print("Food/ drink is above the nose, ignoring.")
                    continue 

                # if area of food/ drink is more than 265% of the area of head, head is likely to be further away so ignore
                # if area of food/ drink is less than 30% of the area of head, food/ drink is likely to be further away so ignore
                area_food_drinks = abs(x1 - x2) * abs(y1 - y2)
                area_head = abs(fx1 - fx2) * abs(fy1 - fy2)
                if (area_food_drinks >= area_head * 2.65 or area_food_drinks < area_head * 0.3):
                    print("Food/ drink not at the same depth as person, ignoring.")
                    continue

                # Delete for the time being. My bottle bigger than my face - Deric
                # height of food/ drinks should not be 1.35 larger than face to be considered, otherwise ignore
                # if (y2 - y1 >= (fy2 - fy1) * 1.35):
                #     print("Food/ drink height is bigger than head, ignoring.")
                #     continue
                
                dist_nose_to_box = get_dist_nose_to_box(p, local_incompliance, track_id)
                dist = min(
                    np.linalg.norm(p["left_wrist"] - local_incompliance[track_id][1]),
                    np.linalg.norm(p["right_wrist"] - local_incompliance[track_id][1])
                )

                print("dist_nose_to_box", dist_nose_to_box)
                print("dist", dist)

                if dist <= OWNING_THRESHOLD and dist_nose_to_box <= DRINKING_THRESHOLD:
                    print("INSIDE")
                    now = time.time()
                        
                    # Track wrist proximity times
                    if track_id not in wrist_proximity_history:
                        wrist_proximity_history[track_id] = []

                    wrist_proximity_history[track_id].append(now)
                    # print("wrist_proximity_history", wrist_proximity_history)

                    # Logging detection frame per track_Id
                    for track_id, timestamps in wrist_proximity_history.items():
                        print(f"Track ID {track_id} has {len(timestamps)} proximity detections")

                    # Keep only timestamps within the last 2 seconds
                    recent_times = [t for t in wrist_proximity_history[track_id] if now - t <= REQUIRED_DURATION]
                    wrist_proximity_history[track_id] = recent_times  # Prune old entries

                    if len(recent_times) >= REQUIRED_COUNT:
                        # Logging end time of wrist proximity
                        # cv.putText(frame, "CONFIRMED NEAR DRINK", (int(p["nose"][0]), int(p["nose"][1]-10)), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                        face_crop = None
                        face_crop = safe_crop(frame, fx1, fy1, fx2, fy2, padding=30)
                                                        
                        if face_crop is not None and face_crop.size > 0:
                            try:
                                query_embedding = DeepFace.represent(img_path=face_crop, model_name="Facenet", max_faces=1)[0]["embedding"]
                                
                                # find match in database
                                query = """ SELECT DetectionId, distance FROM Embeddings WHERE embeddings MATCH ?
                                ORDER BY distance ASC LIMIT 1; """
                                cursor = db.execute(query, (serialize_float32(query_embedding),)) # euclidean distance
                                row = cursor.fetchone()
                                
                                closest_dist = None
                                if row is not None:
                                    closest_dist = row[1]

                                # match found
                                if closest_dist is not None and closest_dist < FACE_DISTANCE_THRESHOLD:
                                    
                                    detection_id = row[0]
                                    current_date = datetime.now().strftime("%Y-%m-%d")
                                    
                                    query = """ SELECT p.PersonId, p.last_incompliance FROM Snapshot AS s JOIN Person p ON s.person_id = p.PersonId WHERE s.DetectionId = ?;"""
                                    cursor = db.execute(query, (detection_id,))
                                    result = cursor.fetchone()

                                    if result:
                                        person_id, last_incompliance = result
                                        last_date = last_incompliance[:10] if last_incompliance else None

                                        if last_date != current_date and last_date is not None:

                                            # get the existing uuid of face and save incompliance img into folder
                                            save_img(face_crop, str(person_id), current_date, "faces")
                                            save_img(frame, str(person_id), current_date, "incompliances")

                                            update_query = """ UPDATE Person SET last_incompliance = ?, incompliance_count = incompliance_count + 1 WHERE PersonId = ?; """
                                            db.execute(update_query, (current_date, person_id))
                                            snapshot_query = """ INSERT INTO Snapshot (confidence, time_generated, object_detected, imageURL, person_id) VALUES (?, ?, ?, ?, ?) RETURNING DetectionId; """
                                            cursor = db.execute(snapshot_query, (
                                                local_incompliance[track_id][2],  # confidence value
                                                current_date,
                                                str(local_incompliance[track_id][3]),  # detected object class id
                                                f"incompliances/{person_id}/Person_{person_id}_{current_date}.jpg",
                                                person_id
                                            ))
                                            detection_id = cursor.fetchone()[0]
                                            embeddings_query = """ INSERT INTO Embeddings (DetectionId, embeddings) VALUES (?, ?); """
                                            db.execute(embeddings_query, (detection_id, serialize_float32(query_embedding)))
                                            db.commit()

                                            print(f"[ACTION] Similar face found 🟢: {person_id}. Saving incompliance snapshot and updated last incompliance date ✅")
                                            
                                        # incompliance on the same date
                                        else:
                                            print(f"[ACTION] 🟣🟣🟣🟣 Similar face found but incompliance on same date, ignoring.")

                                        with flagged_foodbev_lock:
                                            flagged_foodbev.append(track_id) # save track id of bottle
                                # no match
                                else:
                                    with flagged_foodbev_lock:
                                        flagged_foodbev.append(track_id) # save track id of bottle

                                    current_date = datetime.now().strftime("%Y-%m-%d")

                                    cursor = db.execute(""" INSERT INTO Person (last_incompliance, incompliance_count) VALUES (?, 1) RETURNING PersonId;""", (current_date,))
                                    person_id = cursor.fetchone()[0]

                                    os.makedirs(os.path.join("static", "incompliances", str(person_id)), exist_ok=True)
                                    # save cropped face area save it for matching next time
                                    os.makedirs(os.path.join("static", "faces", str(person_id)), exist_ok=True)

                                    snapshot_query = """ INSERT INTO Snapshot (confidence, time_generated, object_detected, imageURL, person_id) VALUES (?, ?, ?, ?, ?) RETURNING DetectionId; """
                                    cursor = db.execute(snapshot_query, (
                                        local_incompliance[track_id][2],  # confidence value
                                        current_date,
                                        str(local_incompliance[track_id][3]),  # detected object class id
                                        f"incompliances/{person_id}/Person_{person_id}_{current_date}.jpg",
                                        person_id
                                    ))
                                    detection_id = cursor.fetchone()[0]
                                    embeddings_query = """ INSERT INTO Embeddings (DetectionId, embeddings) VALUES (?, ?); """
                                    db.execute(embeddings_query, (detection_id, serialize_float32(query_embedding)))
                                    db.commit()
                                    
                                    save_img(face_crop, str(person_id), current_date, "faces")
                                    save_img(frame, str(person_id), current_date, "incompliances")

                                    print(f"[NEW] No face found 🟡. Saving incompliance snapshot and updated last incompliance date ✅")

                            except Exception as e:
                                print(e)
                                continue

    db.close()                


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    print("[STREAM] Client connected to /video_feed")
    def generate_stream():
        global display_queue
        while running:
            try:
                frame = display_queue.get(timeout=1)
            except queue.Empty:
                continue

            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    def run_app():
        app.run(debug=True, use_reloader=False)

    try:
        read_thread = threading.Thread(target=read_frames)
        inference_thread = threading.Thread(target=preprocess, args=(drink_model, food_model, pose_model, beverage_class_list, food_class_list, 0.3), daemon=True)
        detection_thread = threading.Thread(target=detection)
        save_thread = threading.Thread(target=image_saver, daemon=True)
        flask_thread = threading.Thread(target=run_app, daemon=True)

        read_thread.start()
        inference_thread.start()
        detection_thread.start()
        save_thread.start()
        flask_thread.start()

        try:
            while running:
                time.sleep(1)
        except KeyboardInterrupt:
            running = False


        read_thread.join()
        detection_thread.join()

            
    finally:
        running = False
        cap.release()

        print(f"[END]")