import queue, time, os
import numpy as np
from datetime import datetime
from threads.saver import save_img

import time
from threads.emailservice import EmailService  
from threads.nvr import NVR
from threads.process_incompliance import ProcessIncompliance
from shared.camera import Camera

# Constants
REQUIRED_DURATION = 2.0  # seconds
REQUIRED_COUNT = 3  # Number of detections in that duration
FACE_DISTANCE_THRESHOLD = 10
DATABASE = 'users.sqlite'

def safe_crop(img, x1, y1, x2, y2, padding=0):
    h, w, _ = img.shape
    x1 = max(x1 - padding, 0)
    y1 = max(y1 - padding, 0)
    x2 = min(x2 + padding, w)
    y2 = min(y2 + padding, h)
    return img[y1:y2, x1:x2]

# Estimates the facial area based on the nose, eyes and ears
def extract_face_from_nose(pose_points, frame):
    h, _ = frame.shape[:2]

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
    x1 = int(min(l_ear[0], r_eye[0] - 40))
    x2 = int(max(r_ear[0], l_eye[0] + 40))

    # check that bbox is valid
    if x2 <= x1 or y2 <= y1:
        print(x1, y1, x2, y2)
        raise ValueError("Invalid bounding box dimensions.")

    return (x1, y1, x2, y2)

def get_dist_nose_to_box(pose_points, food_drinks_bbox):

    # Compute edge of food/drink bbox edges to nose point
    # Get nose point
    nose = np.array(pose_points["nose"])

    # Get food/ drinks bounding box coords
    x1, y1, x2, y2 = food_drinks_bbox

    # Clamp the nose to the bounding box (to get closest point on box edge)
    clamped_x = np.clip(nose[0], x1, x2)
    clamped_y = np.clip(nose[1], y1, y2)

    # Compute distance from nose to closest point on the bbox (euclidean distance formula)
    return np.linalg.norm(nose - np.array([clamped_x, clamped_y]))

# Helper function to keep track of track id
def flag_track_id(context, track_id):
    with context.flagged_foodbev_lock:
        context.flagged_foodbev.append(track_id)

# Mapping detected food/ drinks to person
def detection(context: Camera):

    email_service = EmailService()
    nvr = NVR("192.168.1.63", "D3FB23C8155040E4BE08374A418ED0CA", "admin", "Sit12345")
    process_incompliance = ProcessIncompliance(DATABASE, context.camera_id)

    while context.running.is_set():
        try:
            frame = context.process_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # Shallow copy for reading in this thread
        with context.detected_incompliance_lock, context.pose_points_lock:
            local_pose_points = list(context.pose_points)
            local_detected_food_drinks = dict(context.detected_incompliance)

        for p in local_pose_points:
            for track_id in local_detected_food_drinks:

                with context.flagged_foodbev_lock:
                    if track_id in context.flagged_foodbev:
                        continue

                food_drinks_bbox = local_detected_food_drinks[track_id][0]
                food_drinks_center = local_detected_food_drinks[track_id][1]
                x1, y1, x2, y2 = food_drinks_bbox

                try:
                    face_bbox = extract_face_from_nose(p, frame)
                    fx1, fy1, fx2, fy2 = map(int, face_bbox)

                except ValueError:
                    print("can't extract the face")
                    continue

                # If the top of food/ drink bbox is a percentage above the nose, ignore
                if y1 < p["nose"][1] * 0.65:
                    print("Food/ drink is above the nose, ignoring.")
                    continue

                # If area of food/ drink is more than 4 times the area of head, head is likely to be further away so ignore
                # If area of food/ drink is less than 10% of the area of head, food/ drink is likely to be further away so ignore
                area_food_drinks = abs(x1 - x2) * abs(y1 - y2)
                area_head = abs(fx1 - fx2) * abs(fy1 - fy2)
                if (area_food_drinks >= area_head * 4 or area_food_drinks < area_head * 0.1):
                    print("Food/ drink not at the same depth as person, ignoring.")
                    continue
                
                # Filter out poses that are too far away
                dist_nose_to_box = get_dist_nose_to_box(p, food_drinks_bbox)
                dist = min(np.linalg.norm(p["left_wrist"] - food_drinks_center), np.linalg.norm(p["right_wrist"] - food_drinks_center))

                # Distance thresholds
                NOSE_THRESHOLD = abs(y1 - y2) * 1.1
                DRINKING_THRESHOLD = abs(y1 - y2) * 0.3
                WRIST_THRESHOLD = abs(y1 - y2) * 0.5

                # Check if drinking
                if dist_nose_to_box > DRINKING_THRESHOLD:
                    # Not drinking, check if holding
                    if dist > WRIST_THRESHOLD or dist_nose_to_box > NOSE_THRESHOLD:
                        # Not holding, skip
                        continue
 
                now = time.time()

                # Track wrist proximity times
                if track_id not in context.wrist_proximity_history:
                    context.wrist_proximity_history[track_id] = []

                context.wrist_proximity_history[track_id].append(now)

                # Logging detection frame per track_Id
                for track_id, timestamps in context.wrist_proximity_history.items():
                    print(f"Track ID {track_id} has {len(timestamps)} proximity detections")

                # Keep only timestamps within the last 2 seconds
                recent_times = [t for t in context.wrist_proximity_history[track_id] if now - t <= REQUIRED_DURATION]
                context.wrist_proximity_history[track_id] = (recent_times)  # Prune old entries

                if len(recent_times) < REQUIRED_COUNT:
                    continue
                
                face_crop = None
                face_crop = safe_crop(frame, fx1, fy1, fx2, fy2, padding=30)
                
                # Face crop failed
                if face_crop is None or face_crop.size <= 0:
                    continue

                try:
                    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    today = current_date[:10]

                    # Facial Recognition
                    mode_data = nvr.get_mode_data(frame)
                    matches_found = nvr.get_face_comparison(mode_data)
                    
                    if matches_found[0] == None:
                        continue

                    # Match found
                    if int(matches_found[0]) >= 1:

                        print("Match found")
                        person_id = process_incompliance.match_found_new_incompliance(matches_found, nvr, local_detected_food_drinks, track_id, face_crop, current_date)

                        # Incompliance on different date
                        if person_id is not None:
                                            
                            # Save frame locally
                            save_img(context, frame, str(person_id), today)
                
                            # Send Email for Second Incompliance Detected
                            email_service.send_incompliance_email("koitristan123@gmail.com", f"Person {person_id}")
                            
                            print(f"[ACTION] Similar face found 🟢: {person_id}. Saving incompliance snapshot and updated last incompliance date ✅")
                            
                        # Incompliance on the same date
                        else:
                            print("[ACTION] 🟣🟣🟣🟣 Similar face found but incompliance on same date, ignoring.")
                            # email_service.send_incompliance_email("koitristan123@gmail.com", f"Person {person_id}")


                        flag_track_id(context, track_id)

                    # No match found
                    elif int(matches_found[0]) < 1:
                        print("No match found")
                        flag_track_id(context, track_id)

                        person_id = process_incompliance.no_match_new_incompliance(nvr, local_detected_food_drinks, track_id, face_crop, current_date)
                        
                        # Save frame locally in new folder
                        os.makedirs(os.path.join("web", "static", "incompliances", str(person_id),), exist_ok=True,)
                        save_img(context, frame, str(person_id), today)
                        
                        print("[NEW] No face found 🟡. Saving incompliance snapshot and updated last incompliance date ✅")
                        time.sleep(3)  # Give time for the face to be modeled in NVR, prevents double inserts of same incompliances
                        # email_service.send_incompliance_email("koitristan123@gmail.com", f"Person {person_id}")


                except Exception as e:
                    print(e)
                    continue

    process_incompliance.close_connection()