import queue, os
from datetime import datetime, timedelta
import cv2 as cv
from ultralytics import YOLO
from shared.camera import Camera

# Display annotated frames on dashboard
def preprocess(context: Camera, target_classes_id, conf_threshold):
    
    drink_model = YOLO(os.path.join("yolo_models", "yolo11n.pt"))
    pose_model = YOLO(os.path.join("yolo_models", "yolov8n-pose.pt"))
    last_cleared = datetime.min

    while context.running.is_set():
        
        try:
            frame = context.frame_queue.get(timeout=1)

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
            frame,
            persist=True,
            classes=target_classes_id,
            conf=conf_threshold,
            verbose=False,
        )
        drink_boxes = result[0].boxes

        with context.detected_incompliance_lock:
            context.detected_incompliance.clear()

        if drink_boxes and len(drink_boxes) >= 1:
            # or (food_boxes and len(food_boxes) >= 1)):

            if datetime.now() - last_cleared >= timedelta(hours=2): # Clear flagged ids every 2 hours
                with context.flagged_foodbev_lock:
                    context.flagged_foodbev.clear()
                last_cleared = datetime.now()

            # object detection pipeline
            with context.detected_incompliance_lock:
                # Process drinks
                for box in drink_boxes:
                    track_id = int(box.id) if box.id is not None else None
                    if (track_id is None):
                        continue

                    cls_id = int(box.cls.cpu())
                    confidence = float(box.conf.cpu())
                    coords = box.xyxy[0].cpu().numpy()
                    # class_name = drink_model.names[cls_id]
                    # print(
                    #     f"[Food/Drink] {class_name} (ID: {cls_id}) - {confidence:.2f}"
                    # )

                    x1, y1, x2, y2 = map(int, coords)

                    cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv.putText(frame_copy, f"id: {track_id}, conf: {confidence:.2f}", (x1, y1 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                    if (track_id not in context.flagged_foodbev):
                        context.detected_incompliance[track_id] = [
                            coords, # Coordinates of bbox
                            (
                                (coords[0] + coords[2]) // 2, # Center of bbox
                                (coords[1] + coords[3]) // 2,
                            ),
                            confidence, # Confidence score
                            cls_id, # Class Id of detected object (refer to COCO dataset)
                        ]

            pose_results = pose_model.predict(frame, conf=0.80, iou=0.4, verbose=False)[
                0
            ]
            keypoints = pose_results.keypoints.xy if pose_results.keypoints else []
            with context.pose_points_lock:
                context.pose_points.clear()

            with context.detected_incompliance_lock and context.pose_points_lock:
                # only process if theres both faces and food/beverages in frame
                if context.detected_incompliance and (keypoints is not None):
                    # save landmarks for each person
                    for person in keypoints:
                        try:
                            person_lm = person.cpu().numpy()
                            context.pose_points.append(
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
            with context.detected_incompliance_lock and context.pose_points_lock:
                if context.pose_points and context.detected_incompliance:
                    try:
                        if not context.process_queue.full():
                            context.process_queue.put(frame)

                        else:
                            try:
                                context.process_queue.get_nowait()
                            except queue.Empty:
                                pass
                            context.process_queue.put(frame)

                    except Exception as e:
                        print(f"Error putting frame into process queue: {e}")

        # Put into queue to display frames in dashboard
        if not context.display_queue.full():
            context.display_queue.put(frame_copy)
        else:
            try:
                context.display_queue.get_nowait()
            except queue.Empty:
                pass
            context.display_queue.put(frame_copy)
