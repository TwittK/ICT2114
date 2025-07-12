import queue, time, os
import numpy as np
from datetime import datetime
from threads.saver import save_img
from shared.state import (
    process_queue,
    running,
    detected_incompliance_lock,
    pose_points_lock,
    pose_points,
    detected_incompliance,
    flagged_foodbev_lock,
    flagged_foodbev,
    wrist_proximity_history,
)
import time
import shared.state as shared_state
from threads.emailservice import EmailService  
from threads.nvr import NVR
from threads.process_incompliance import ProcessIncompliance

# Constants
NOSE_THRESHOLD = 300  # Distance thresholds
WRIST_THRESHOLD = 170
REQUIRED_DURATION = 2.0  # seconds
REQUIRED_COUNT = 3  # number of detections in that duration
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
    x1 = int(min(l_ear[0], r_eye[0] - 40))
    x2 = int(max(r_ear[0], l_eye[0] + 40))

    # check that bbox is valid
    if x2 <= x1 or y2 <= y1:
        print(x1, y1, x2, y2)
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


# Associate detected food/ drinks to personsss
def detection():
    # global runningsssssssssssssssssssssssss
    # global save_queue, process_queue
    # global detected_food_drinks_lock, pose_points_lock, flagged_foodbev_lock
    # global flagged_foodbev, pose_points, detected_food_drinks
    # global wrist_proximity_history

    email_service = EmailService()
    nvr = NVR("192.168.1.63", "D3FB23C8155040E4BE08374A418ED0CA", "admin", "Sit12345")
    process_incompliance = ProcessIncompliance("users.sqlite")

    while shared_state.running:
        try:
            frame = process_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # shallow copy for reading in this thread
        with detected_incompliance_lock, pose_points_lock:
            local_pose_points = list(pose_points)
            local_detected_food_drinks = dict(detected_incompliance)

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
                    print("can't extract the face")
                    continue

                # if the top of food/ drink bbox is a percentage above the nose, ignore
                if y1 < p["nose"][1] * 0.95:
                    print("Food/ drink is above the nose, ignoring.")
                    continue

                # if area of food/ drink is more than 3.65 times the area of head, head is likely to be further away so ignore
                # if area of food/ drink is less than 10% of the area of head, food/ drink is likely to be further away so ignore
                area_food_drinks = abs(x1 - x2) * abs(y1 - y2)
                area_head = abs(fx1 - fx2) * abs(fy1 - fy2)
                if (area_food_drinks >= area_head * 3.65 or area_food_drinks < area_head * 0.1):
                    print("Food/ drink not at the same depth as person, ignoring.")
                    continue

                dist_nose_to_box = get_dist_nose_to_box(p, local_detected_food_drinks, track_id)
                dist = min(
                    np.linalg.norm(
                        p["left_wrist"] - local_detected_food_drinks[track_id][1]
                    ),
                    np.linalg.norm(
                        p["right_wrist"] - local_detected_food_drinks[track_id][1]
                    ),
                )
                if dist <= WRIST_THRESHOLD and dist_nose_to_box <= NOSE_THRESHOLD:

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
                    wrist_proximity_history[track_id] = (recent_times)  # Prune old entries

                    if len(recent_times) >= REQUIRED_COUNT:
                        face_crop = None
                        face_crop = safe_crop(frame, fx1, fy1, fx2, fy2, padding=30)

                        if face_crop is not None and face_crop.size > 0:
                            try:
                                # modeData = nvr.get_mode_data(frame)
                                # matchesFound = nvr.get_face_comparison(modeData)
                                matchesFound = (0, "fdsjf342")

                                # match found
                                if matchesFound is not None and int(matchesFound[0]) >= 1:

                                    print("Match found")
                                    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    today = current_date[:10]

                                    person_id = process_incompliance.match_found_new_incompliance(nvr, local_detected_food_drinks, track_id, face_crop, frame, current_date, today)

                                    if person_id is not None:
                                                        
                                        # Save frame locally
                                        save_img(frame, str(person_id), today, "incompliances",)
                            
                                        # Send Email for Second Incompliance Detected
                                        email_service.send_incompliance_email("koitristan123@gmail.com", f"Person {person_id}")
                                        
                                        print(f"[ACTION] Similar face found 🟢: {person_id}. Saving incompliance snapshot and updated last incompliance date ✅")
                                        
                                    # Incompliance on the same date
                                    else:
                                        print(f"[ACTION] 🟣🟣🟣🟣 Similar face found but incompliance on same date, ignoring.")

                                    with flagged_foodbev_lock:
                                        flagged_foodbev.append(track_id)

                                # No match
                                elif matchesFound is not None and int(matchesFound[0]) < 1:
                                    print("No match found")
                                    with flagged_foodbev_lock:
                                        flagged_foodbev.append(track_id)

                                    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    today = current_date[:10]

                                    person_id = process_incompliance.no_match_new_incompliance(nvr, local_detected_food_drinks, track_id, face_crop, frame, current_date, today)
                                    
                                    # Save frame locally in new folder
                                    os.makedirs(os.path.join("web", "static", "incompliances", str(person_id),), exist_ok=True,)
                                    save_img(frame, str(person_id), today, "incompliances",)
                                    
                                    print(f"[NEW] No face found 🟡. Saving incompliance snapshot and updated last incompliance date ✅")
                                    time.sleep(3)  # Give time for the face to be modeled in NVR, prevents double inserts of same incompliances

                            except Exception as e:
                                print(e)
                                continue
                else:
                    print("Pose not near drink, skipping.")

    process_incompliance.close_connection()