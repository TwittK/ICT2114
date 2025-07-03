import sqlite3, sqlite_vec
from sqlite_vec import serialize_float32
import queue, time, os
import numpy as np
from deepface import DeepFace
from datetime import datetime
from threads.saver import save_img
from shared.state import process_queue, running, detected_food_drinks_lock, pose_points_lock, pose_points, detected_food_drinks, flagged_foodbev_lock, flagged_foodbev, wrist_proximity_history

# Constants
DRINKING_THRESHOLD = 50 # Distance thresholds
OWNING_THRESHOLD = 100
REQUIRED_DURATION = 2.0  # seconds
REQUIRED_COUNT = 7      # number of detections in that duration
FACE_DISTANCE_THRESHOLD = 10

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

# Associate detected food/ drinks to person
def detection():
    # global running
    # global save_queue, process_queue
    # global detected_food_drinks_lock, pose_points_lock, flagged_foodbev_lock
    # global flagged_foodbev, pose_points, detected_food_drinks
    # global wrist_proximity_history

    db = sqlite3.connect("database/test.sqlite")
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
        with detected_food_drinks_lock, pose_points_lock:
            local_pose_points = list(pose_points)
            local_detected_food_drinks = dict(detected_food_drinks)


        for p in local_pose_points:
            for track_id in local_detected_food_drinks:

                with flagged_foodbev_lock:
                    if track_id in flagged_foodbev:
                        continue

                food_drinks_bbox = local_detected_food_drinks[track_id][0] 
                x1, y1, x2, y2 = food_drinks_bbox

                try:
                    face_bbox = extract_face_from_nose(p, frame)
                    fx1, fy1, fx2, fy2 = map(int, face_bbox)

                except ValueError:
                    # print("can't extract the face")
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

                # height of food/ drinks should not be 1.35 larger than face to be considered, otherwise ignore
                if (y2 - y1 >= (fy2 - fy1) * 1.35):
                    print("Food/ drink height is bigger than head, ignoring.")
                    continue
                
                dist_nose_to_box = get_dist_nose_to_box(p, local_detected_food_drinks, track_id)
                dist = min(
                    np.linalg.norm(p["left_wrist"] - local_detected_food_drinks[track_id][1]),
                    np.linalg.norm(p["right_wrist"] - local_detected_food_drinks[track_id][1])
                )

                if dist <= OWNING_THRESHOLD and dist_nose_to_box <= DRINKING_THRESHOLD:

                    now = time.time()
                        
                    # Track wrist proximity times
                    if track_id not in wrist_proximity_history:
                        wrist_proximity_history[track_id] = []

                    wrist_proximity_history[track_id].append(now)

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
                                                local_detected_food_drinks[track_id][2],  # confidence value
                                                current_date,
                                                str(local_detected_food_drinks[track_id][3]),  # detected object class id
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
                                        local_detected_food_drinks[track_id][2],  # confidence value
                                        current_date,
                                        str(local_detected_food_drinks[track_id][3]),  # detected object class id
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