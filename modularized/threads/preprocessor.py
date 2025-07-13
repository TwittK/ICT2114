import queue, os
from datetime import datetime
import cv2 as cv
from ultralytics import YOLO
from shared.state import (
    frame_queue,
    detected_incompliance_lock,
    detected_incompliance,
    flagged_foodbev_lock,
    flagged_foodbev,
    pose_points_lock,
    pose_points,
    process_queue,
    display_queue,
)
import shared.state as shared_state

# Display annotated frames on dashboard
def preprocess(target_classes_id, conf_threshold):
    # global running
    # global frame_queue, process_queue, display_queue
    # global detected_food_drinks_lock, pose_points_lock, flagged_foodbev_lock
    # global flagged_foodbev, pose_points, detected_food_drinks

    drink_model = YOLO(os.path.join("yolo_models", "yolo11n.pt"))
    pose_model = YOLO(os.path.join("yolo_models", "yolov8n-pose.pt"))
    last_cleared_day = None

    while shared_state.running:
        try:
            frame = frame_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # perform image processing here
        frame_copy = (
            frame.copy()
        )  # copy frame for drawing bounding boxes, ids and conf scores.

        # Drink detection
        result = drink_model.track(
            frame_copy,
            persist=True,
            classes=target_classes_id,
            conf=conf_threshold,
            iou=0.4,
            verbose=False,
        )
        drink_boxes = result[0].boxes

        with detected_incompliance_lock:
            detected_incompliance.clear()

        if drink_boxes and len(drink_boxes) >= 1:
            # or (food_boxes and len(food_boxes) >= 1)):

            current_day = datetime.now().date()
            if last_cleared_day != current_day:  # refresh flagged track ids daily
                with flagged_foodbev_lock:
                    flagged_foodbev.clear()
                last_cleared_day = current_day

            # object detection pipeline
            with detected_incompliance_lock:
                # Process drinks
                for box in drink_boxes:
                    track_id = int(box.id) if box.id is not None else None
                    cls_id = int(box.cls.cpu())
                    confidence = float(box.conf.cpu())
                    coords = box.xyxy[0].cpu().numpy()
                    class_name = drink_model.names[cls_id]
                    # print(
                    #     f"[Food/Drink] {class_name} (ID: {cls_id}) - {confidence:.2f}"
                    # )

                    x1, y1, x2, y2 = map(int, coords)

                    if track_id is not None and track_id not in flagged_foodbev:
                        detected_incompliance[track_id] = [
                            coords,
                            (
                                (coords[0] + coords[2]) // 2,
                                (coords[1] + coords[3]) // 2,
                            ),
                            confidence,
                            cls_id,
                        ]
                        cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv.putText(
                            frame_copy,
                            f"id: {track_id}, conf: {confidence:.2f}",
                            (x1, y1 - 10),
                            cv.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255),
                            2,
                        )

            pose_results = pose_model.predict(frame, conf=0.80, iou=0.4, verbose=False)[
                0
            ]
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
                            pose_points.append(
                                {
                                    "nose": person_lm[0],
                                    "left_wrist": person_lm[9],
                                    "right_wrist": person_lm[10],
                                    "left_ear": person_lm[3],
                                    "right_ear": person_lm[4],
                                    "left_eye": person_lm[1],
                                    "right_eye": person_lm[2],
                                }
                            )
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
