import queue, time, os, csv
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from datetime import datetime
import cv2
from zoneinfo import ZoneInfo

import time
from threads.notificationservice import NotificationService
from threads.nvr import NVR
from threads.process_incompliance import ProcessIncompliance
from shared.camera import Camera
from database import get_lab_safety_email_by_camera_id
from database import get_lab_safety_telegram_by_camera_id

from shared.mqtt_client import MQTTClient
from data_source.lab_safety_staff_dao import LabSafetyStaffDAO

# Constants
REQUIRED_DURATION = 2.0  # seconds
REQUIRED_COUNT = 3  # Number of detections in that duration
# DATABASE = 'users.sqlite'
load_dotenv()
db_params = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

mqtt_client = MQTTClient()
lab_safety_staff_dao = LabSafetyStaffDAO(db_params=db_params)

def save_to_csv(frames_processed, avg_confidence, timestamp, tile_folder, total_detections, total_associations):
    """Save metrics to CSV file with detection statistics"""
    file_path = 'confidence_metrics.csv'
    
    file_exists = os.path.exists(file_path)
    
    with open(file_path, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                'Timestamp',
                'Tile Configuration', 
                'Frames Processed',
                'Average Confidence',
                'Total Detections',
                'Successful Associations',
                'False Negatives',
                'Association Rate'
            ])
        
        # Calculate false negatives (detections that should have been associated but weren't)
        false_negatives = total_detections - total_associations
        association_rate = (total_associations / total_detections) if total_detections > 0 else 0
        
        writer.writerow([
            timestamp,
            tile_folder,
            frames_processed,
            f"{avg_confidence:.3f}",
            total_detections,
            total_associations,
            false_negatives,
            f"{association_rate:.2%}"
        ])


def safe_crop(img, x1, y1, x2, y2, padding=0):
    """
    Safely crops a region from an image, ensuring the crop area stays within image boundaries.

    Parameters:
        img (np.ndarray): The frame from which to crop.
        x1, y1 (int): Top-left coordinates of the crop rectangle.
        x2, y2 (int): Bottom-right coordinates of the crop rectangle.
        padding (int, optional): Number of pixels to expand the crop area in all directions. Default is 0.

    Returns:
        np.ndarray: Cropped image region with padding applied, clipped to the image size.
    """
    h, w, _ = img.shape
    x1 = max(x1 - padding, 0)
    y1 = max(y1 - padding, 0)
    x2 = min(x2 + padding, w)
    y2 = min(y2 + padding, h)
    return img[y1:y2, x1:x2]


# Estimates the facial area based on the nose, eyes and ears
def extract_face_from_nose(pose_points, frame):
    """
    Estimates a bounding box for the face based on detected keypoints: nose, eyes, and ears.

    The bounding box is calculated vertically using the distance from nose to eyes (value is tripled),
    and horizontally using the ears and eye positions with some offsets.

    Parameters:
        pose_points (dict): Dictionary that has 'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear' keypoints as (x, y) tuples.
        frame (np.ndarray): The frame from which to extract the face area.

    Returns:
        tuple: Coordinates (x1, y1, x2, y2) defining the bounding box of the estimated face region.

    Raises:
        ValueError: If the calculated bounding box dimensions are invalid (x2 <= x1 or y2 <= y1).
    """
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
    """
    Calculates the shortest Euclidean distance from the nose keypoint to the edges of a given bounding box.

    Parameters:
        pose_points (dict): Dictionary containing 'nose' keypoint as an (x, y) tuple.
        food_drinks_bbox (tuple): Coordinates (x1, y1, x2, y2) of the bounding box representing food or drink.

    Returns:
        float: The Euclidean distance between the nose point and the closest edge of the bounding box.
    """
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
def association(context: Camera):
    notifier = NotificationService()
    nvr = NVR("192.168.1.63", "D3FB23C8155040E4BE08374A418ED0CA", "admin", "Sit12345")
    process_incompliance = ProcessIncompliance(db_params, context.camera_id)
    # process_incompliance = ProcessIncompliance(DATABASE, context.camera_id)
    frames_processed = 0 
    total_detections = 0
    total_associations = 0
    
    while context.running.is_set():
        try:
            frame = context.process_queue.get(timeout=1)
            frames_processed += 1  # Increment counter
            

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # Shallow copy for reading in this thread
        with context.detected_incompliance_lock, context.pose_points_lock:
            local_pose_points = list(context.pose_points)
            local_detected_food_drinks = dict(context.detected_incompliance)
            # Count detections in current frame
            total_detections += len(local_detected_food_drinks)

        # Log metrics every 5 frames
        if frames_processed % 5 == 0:
            print(f"[INFO] Processing frame {frames_processed}")
            confidence_scores = [
                detection[2] 
                for detection in local_detected_food_drinks.values()
                if len(detection) > 2
            ]
            
            if confidence_scores:
                avg_confidence = sum(confidence_scores) / len(confidence_scores)
                print("avg_confidence:", avg_confidence)
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # Get exact folder name from context
                tile_folder = getattr(context, 'current_tile_folder', 'unknown')
                save_to_csv(
                    frames_processed,
                    avg_confidence,
                    timestamp,
                    tile_folder,
                    total_detections,
                    total_associations
                )

        print(f"🔄 Frame {frames_processed} | Detections: {total_detections} | Associations: {total_associations}")

        if frame is None or frame.size == 0:
            continue

        best_matches = {}
        for track_id in local_detected_food_drinks:
            with context.flagged_foodbev_lock:
                if track_id in context.flagged_foodbev:
                    continue

        best_matches = {}
        for track_id in local_detected_food_drinks:

            with context.flagged_foodbev_lock:
                if track_id in context.flagged_foodbev:
                    continue

            food_drinks_bbox = local_detected_food_drinks[track_id][0]
            food_drinks_center = local_detected_food_drinks[track_id][1]
            x1, y1, x2, y2 = map(int, food_drinks_bbox)

            drink = frame.copy()
            cv2.rectangle(drink, (x1, y1), (x2, y2), (0, 255, 0), 2)
            best_score = float("inf")
            best_matches[track_id] = {"person": None, "best_score": best_score}

            for p in local_pose_points:

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

                # If height of food/ drink is a lot larger than height head, person is likely to be further away so ignore
                # If height of food/ drink is a lot smaller than height of head, food/ drink is likely to be further away so ignore
                area_food_drinks = abs(x1 - x2) * abs(y1 - y2)
                area_head = abs(fx1 - fx2) * abs(fy1 - fy2)
                area_check = (
                        area_food_drinks >= area_head * 4
                        or area_food_drinks < area_head * 0.1
                )
                height_check = (
                        abs(y1 - y2) >= abs(fy1 - fy2) * 2.85
                        or abs(y1 - y2) < abs(fy1 - fy2) * 0.35
                )
                if area_check or height_check:
                    # print("🔶Food/ drink not at the same depth as person, ignoring.")
                    continue

                # Filter out poses that are too far away
                dist_nose_to_box = get_dist_nose_to_box(p, food_drinks_bbox)
                dist = min(
                    np.linalg.norm(p["left_wrist"] - food_drinks_center),
                    np.linalg.norm(p["right_wrist"] - food_drinks_center),
                )

                # Distance thresholds
                nose_threshold = abs(y1 - y2) * 1.1
                consumption_threshold = abs(y1 - y2) * 0.3
                wrist_threshold = abs(y1 - y2) * 0.5

                # Check if drinking
                if dist_nose_to_box > consumption_threshold:
                    # Not drinking, check if holding
                    if dist > wrist_threshold or dist_nose_to_box > nose_threshold:
                        # Not holding, skip
                        continue

                # Find best matched person
                score = dist_nose_to_box + dist
                if score < best_matches[track_id]["best_score"]:
                    best_matches[track_id]["best_score"] = score
                    best_matches[track_id]["person"] = p

            if best_matches[track_id]["person"] is not None:
                print("✅ Found association for track ID:", track_id)
                total_associations += 1
                p = best_matches[track_id]["person"]
                now = time.time()

                # Track wrist proximity times
                if track_id not in context.wrist_proximity_history:
                    context.wrist_proximity_history[track_id] = []

                context.wrist_proximity_history[track_id].append(now)

                # # Logging detection frame per track_Id
                # for track_id, timestamps in context.wrist_proximity_history.items():
                #     print(
                #         f"Track ID {track_id} has {len(timestamps)} proximity detections"
                #     )

                # Keep only timestamps within the last 2 seconds
                recent_times = [
                    t
                    for t in context.wrist_proximity_history[track_id]
                    if now - t <= REQUIRED_DURATION
                ]
                context.wrist_proximity_history[track_id] = (
                    recent_times  # Prune old entries
                )

                if len(recent_times) < REQUIRED_COUNT:
                    continue

                face_crop = None
                try:
                    face_bbox = extract_face_from_nose(p, frame)
                    fx1, fy1, fx2, fy2 = map(int, face_bbox)

                except ValueError:
                    print("can't extract the face")
                    continue
                face_crop = safe_crop(frame, fx1, fy1, fx2, fy2, padding=30)

                # Face crop failed
                if face_crop is None or face_crop.size <= 0:
                    continue

                try:
                    # Mock next day
                    mocked_date = datetime(2025, 11, 2)
                    current_date = mocked_date.strftime("%Y-%m-%d %H:%M:%S")

                    # local_tz = ZoneInfo("Asia/Singapore")
                    # current_date = datetime.now(local_tz).strftime("%Y-%m-%d %H:%M:%S")
                    print(current_date)
                    today = current_date[:10]

                    # Facial Recognition
                    mode_data = nvr.get_mode_data(frame)
                    matches_found = nvr.get_face_comparison(mode_data)

                    if matches_found[0] == None:
                        continue

                    # Match found
                    if int(matches_found[0]) >= 1:

                        with context.manager.nvr_face_lock:
                            print("Match found")
                            person_id = process_incompliance.match_found_new_incompliance(
                                matches_found,
                                nvr,
                                local_detected_food_drinks,
                                track_id,
                                face_crop,
                                current_date,
                            )
                            # Give time for the face to be modeled in NVR, prevents double inserts of same incompliances
                            time.sleep(3)

                            # Incompliance on different date
                            if person_id is not None:

                                # Save frame locally
                                clone = frame.copy()
                                cv2.rectangle(clone, (fx1, fy1), (fx2, fy2), (0, 0, 255), 1)
                                cv2.rectangle(clone, (x1, y1), (x2, y2), (0, 255, 0), 1)
                                context.manager.saver.save_img(clone, str(person_id), today)

                                # Send Email for Second Incompliance Detected
                                lab_emails = get_lab_safety_email_by_camera_id(
                                    context.camera_id
                                )
                                lab_emails = lab_safety_staff_dao.get_email_by_camera_id(context.camera_id)
                                lab_telegram = get_lab_safety_telegram_by_camera_id(
                                    context.camera_id
                                )

                                print(f"[DEBUG23] Retrieved lab emails for camera {context.camera_id}: {lab_emails}")

                                # Email
                                if lab_emails:
                                    for email in lab_emails:
                                        print(f"[DEBUG23] Sending email to: {email}")
                                        notifier.send_incompliance_email(email, f"Person {person_id}")

                                # Telegram
                                if lab_telegram:
                                    for telegram in lab_telegram:
                                        notifier.send_incompliance_telegram(
                                            telegram=telegram,
                                            person_name=f"Person {person_id}",
                                            camera_id=context.camera_id,
                                        )

                                # Publish MQTT message
                                if mqtt_client:
                                    mqtt_client.publish_violation(
                                        user=str(person_id),
                                        event="lab_safety_violation",
                                        details=f"Incompliance detected at camera {context.camera_id} on {current_date}",
                                    )

                                print(f"[ACTION] Similar face found 🟢: {person_id}. Saving incompliance snapshot and updated last incompliance date ✅")

                        flag_track_id(context, track_id)

                    # No match found
                    elif int(matches_found[0]) < 1:
                        
                        flag_track_id(context, track_id)

                        with context.manager.nvr_face_lock:
                            print("No match found")
                            person_id = process_incompliance.no_match_new_incompliance(
                                nvr,
                                local_detected_food_drinks,
                                track_id,
                                face_crop,
                                current_date,
                            )
                            # Give time for the face to be modeled in NVR, prevents double inserts of same incompliances
                            time.sleep(3)

                            # Save frame locally in new folder
                            os.makedirs(
                                os.path.join(
                                    "web",
                                    "static",
                                    "incompliances",
                                    str(person_id),
                                ),
                                exist_ok=True,
                            )

                            clone = frame.copy()
                            cv2.rectangle(clone, (fx1, fy1), (fx2, fy2), (0, 0, 255), 1)
                            cv2.rectangle(clone, (x1, y1), (x2, y2), (0, 255, 0), 1)
                            context.manager.saver.save_img(clone, str(person_id), today)

                            print("[NEW] No face found 🟡. Saving incompliance snapshot and updated last incompliance date ✅")

                except Exception as e:
                    print(e)
                    continue
