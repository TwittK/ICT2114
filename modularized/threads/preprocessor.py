import queue
from datetime import datetime
import cv2 as cv
from shared.state import frame_queue, running, detected_food_drinks_lock, detected_food_drinks, flagged_foodbev_lock, flagged_foodbev, pose_points_lock, pose_points, process_queue, display_queue


# Display annotated frames on dashboard
def preprocess(model, pose_model, target_classes_id, conf_threshold):
    # global running
    # global frame_queue, process_queue, display_queue
    # global detected_food_drinks_lock, pose_points_lock, flagged_foodbev_lock
    # global flagged_foodbev, pose_points, detected_food_drinks
    
    while running:
        try:
            frame = frame_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # perform image processing here
        frame_copy = frame.copy() # copy frame for drawing bounding boxes, ids and conf scores.
        result = model.track(frame_copy, persist=True, classes=target_classes_id, conf=conf_threshold, iou=0.4, verbose=False)
        boxes = result[0].boxes

        with detected_food_drinks_lock:
            detected_food_drinks.clear()

        # only process if there are at least 1 food/ drink detected
        if len(boxes) >= 1: 

            if datetime.now().strftime("%H:%M") == "00:00": # refresh flagged track ids daily
                with flagged_foodbev_lock:
                    flagged_foodbev.clear()

            # object detection pipeline
            with detected_food_drinks_lock:
                for box in boxes:
                    track_id = int(box.id) if box.id is not None else None
                    cls_id = int(box.cls.cpu())
                    confidence = float(box.conf.cpu())
                    coords = box.xyxy[0].cpu().numpy()
                    
                    x1, y1, x2, y2 = map(int, coords)

                    if track_id is not None:
                        detected_food_drinks[track_id] = [coords, ((coords[0] + coords[2]) // 2, (coords[1] + coords[3]) // 2), confidence, cls_id]
                        cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv.putText(frame_copy, f"id: {track_id}, conf: {confidence:.2f}", (x1, y1 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)


            pose_results = pose_model.track(frame, persist=True, conf=0.5, iou=0.4, verbose=False)[0]
            keypoints = pose_results.keypoints.xy if pose_results.keypoints else []

            with pose_points_lock:
                pose_points.clear()

            with detected_food_drinks_lock and pose_points_lock:
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
            
            # Put into process queue for the next step (mapping food/ drinks to faces)
            with detected_food_drinks_lock and pose_points_lock:   
                if pose_points and detected_food_drinks:    
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