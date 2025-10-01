import queue, os
from datetime import datetime, timedelta
import cv2 as cv
from ultralytics import YOLO
from ultralytics.utils import ThreadingLocked
from shared.camera import Camera
from threads.model import ObjectDetectionModel, PoseDetectionModel, ImageClassificationModel
from threads.collaborative_inference import CollaborativeInference
from threads.detector import safe_crop


# YOLO model food/ drinks detection, pose and water bottle detection.
def preprocess(context: Camera, target_classes_id, conf_threshold):

    # TODO: see if @ThreadingLocked() can be used to save memory (but reduce concurrency)
    models = [
        ObjectDetectionModel("yolo11n.pt", target_classes_id, conf_threshold, 0),
        #ObjectDetectionModel("yolov8n.pt", target_classes_id, conf_threshold),
        #ObjectDetectionModel("yolov8m.pt", target_classes_id, conf_threshold),
    ]

    pose_model = PoseDetectionModel("yolov8n-pose.pt", 0.80, 0.4)
    classif_model = ImageClassificationModel("yolov8n-cls.pt")
    last_cleared = datetime.min
    
    min_votes = len(models) // 2 + 1
    collab_inference = CollaborativeInference(context, models, min_votes)

    while context.running.is_set():
        
        try:
            frame = context.frame_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # Copy frame for drawing bounding boxes, ids and confidence scores on video feed display.
        frame_copy = frame.copy() 
        

        # Collaborative Inference with list of models.
        collab_inf_results = collab_inference.collaborative_inference(frame)

        with context.detected_incompliance_lock:
            context.detected_incompliance.clear()


        if (collab_inf_results):

            # Periodically clear flagged ids every 2 hours.
            if datetime.now() - last_cleared >= timedelta(hours=2):
                with context.flagged_foodbev_lock:
                    context.flagged_foodbev.clear()
                last_cleared = datetime.now()


            with context.detected_incompliance_lock:

                # Match the same objects across model results and filter out those with confidence less than a certain threshold.
                matched_filtered, filtered_confidence, filtered_boxes = collab_inference.process_inference_results(frame_copy, collab_inf_results, 0.5)

                # No detections with more than 50% confidence
                if not matched_filtered:
                    continue

                # Print out all track IDs
                for i, object_group in enumerate(matched_filtered):
                    for object in object_group:
                        track_id = object.id

                        if track_id is None:
                            continue

                        # Pass crops of detected objects into classification model to filter out water bottles
                        if (track_id not in context.flagged_foodbev):

                            # Check if it's a water bottle or not
                            x1, y1, x2, y2 = map(int, filtered_boxes[i])
                            object_crop = safe_crop(frame, x1, y1, x2, y2, padding=10)
                            results = classif_model.classify(object_crop)
                            pred = results[0]
                            label = pred.names[pred.probs.top1]

                            # Discard saving coordinates if it's a water bottle (model tends to detect some bottles as milk can also)
                            if label == "water_bottle" or label == "milk_can":
                                print("🚫 Water bottle, skipping")
                                continue

                            context.detected_incompliance[track_id.item()] = [
                                filtered_boxes[i], # Coordinates of bbox
                                (
                                    (filtered_boxes[i][0] + filtered_boxes[i][2]) // 2, # Center of bbox
                                    (filtered_boxes[i][1] + filtered_boxes[i][3]) // 2,
                                ),
                                filtered_confidence[i], # Confidence score
                                object.cls.item(), # Class Id of detected object (refer to COCO dataset)
                            ]
                        # print(context.detected_incompliance[track_id])

            keypoints = pose_model.predict(frame)
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