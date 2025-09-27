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
def preprocess(context: Camera, frame, models, pose_model, classif_model):
    if frame is None or frame.size == 0:
        return
    
    # Periodically clear flagged ids every 2 hours.
    last_cleared = datetime.min
    if datetime.now() - last_cleared >= timedelta(hours=2):
        with context.flagged_foodbev_lock:
            context.flagged_foodbev.clear()
        last_cleared = datetime.now()

    # Copy for dashboard display. This copy will have annotations on it.
    frame_copy = frame.copy()

    # At least half + 1 of the models should have at least 1 detection.
    min_votes = len(models) // 2 + 1
    collab_inference = CollaborativeInference(context, models, min_votes)

    # Collaborative Inference with list of models.
    collab_inf_results = collab_inference.collaborative_inference(frame)

    with context.detected_incompliance_lock:
        context.detected_incompliance.clear()

    if (collab_inf_results):

        with context.detected_incompliance_lock:

            # Match the same objects across model results and filter out those with confidence less than a certain threshold.
            matched_filtered, filtered_confidence, filtered_boxes = collab_inference.process_inference_results(frame_copy, collab_inf_results, 0.5)

            # No detections with more than 50% confidence
            if not matched_filtered:
                return

            # Print out all track IDs
            for i, object_group in enumerate(matched_filtered):
                for object in object_group:
                    track_id = object.id
                    if track_id is None:
                        continue
                    
            # TODO: Pass crops of detected objects into classification model to filter out water bottles

    #             if (track_id not in context.flagged_foodbev):

    #                 # Check if it's a water bottle or not
    #                 object_crop = safe_crop(frame, x1, y1, x2, y2, padding=10)
    #                 results = classif_model(object_crop, verbose=False)
    #                 pred = results[0]
    #                 label = pred.names[pred.probs.top1]

    #                 # Discard saving coordinates if it's a water bottle (model tends to detect some bottles as milk can also)
    #                 if label == "water_bottle" or label == "milk_can":
    #                     print("🚫 Water bottle, skipping")
    #                     continue

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

    # Put into camera's display queue to display frames on dashboard video feed
    if not context.display_queue.full():
        context.display_queue.put(frame_copy)
    else:
        try:
            context.display_queue.get_nowait()
        except queue.Empty:
            pass
        context.display_queue.put(frame_copy)

    with context.detected_incompliance_lock and context.pose_points_lock:

        # Return frame for the next step: associating humans with food/ drinks
        if context.pose_points and context.detected_incompliance:
            return frame
        
        return None

