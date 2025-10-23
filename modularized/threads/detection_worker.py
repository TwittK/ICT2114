import queue
from datetime import datetime, timedelta
import cv2 as cv
from shared.model import (
    ObjectDetectionModel,
    PoseDetectionModel,
    ImageClassificationModel,
)
from threads.association import safe_crop
import threading
import queue


class DetectionWorker:
    """
    A worker class responsible for detecting food, drinks, and pose points in video frames.

    This class runs in a separate thread and continuously processes frames from a queue. It applies
    object detection to identify food and beverage items. Filters out objects that could be Water Bottles and performs pose detection
    to identify keypoints/ humans. Detected frames are then sent to the next processing
    stage and also sent to a queue that stores the frames for display on the dashboard.

    Attributes:
        worker_id (int): The unique identifier for this worker.
        queue (queue.Queue): A queue for frames to be processed.
        thread (threading.Thread): The thread that runs the `preprocess` method.
        running (threading.Event): A flag to signal when the worker is running.
    """

    def __init__(self, worker_id):
        """
        Initializes the detection worker with a unique worker ID and starts the worker thread.

        Parameters:
            worker_id (int): The unique identifier for this worker.
        """
        self.queue = queue.Queue()
        self.thread = threading.Thread(
            target=self.preprocess,
            args=(worker_id,),
            name=f"DetectionWorker-{worker_id}",
            daemon=True,
        )
        self.running = threading.Event()
        self.running.set()
        self.thread.start()
        self.worker_id = worker_id

    # Display annotated frames on dashboard
    def preprocess(self, gpu_id):
        """
        Processes frames by detecting food, drinks, and pose keypoints.
        This method continuously retrieves frames from the queue, performs object detection,
        classifies detected objects, and detects human poses.

        Detected food and drink items are checked for compliance (water bottles are ignored).
        Pose keypoints are extracted if both food and poses are detected in the same frame.
        Processed frames are sent to the next processing stage or displayed.

        Parameters:
            gpu_id (int): The ID of the GPU device used for inference.
        """

        object_detection_model = ObjectDetectionModel("yolo11x.pt", gpu_device=gpu_id)
        pose_model = PoseDetectionModel("yolov8n-pose.pt", 0.8, 0.7)
        classif_model = ImageClassificationModel("yolov8n-cls.pt")
        last_cleared = datetime.min

        while self.running.is_set():

            try:
                frame, context = self.queue.get(timeout=1)

            except queue.Empty:
                continue

            if frame is None or frame.size == 0:
                continue

            # perform image processing here
            frame_copy = (
                frame.copy()
            )  # copy frame for drawing bounding boxes, ids and conf scores.

            # Food/Drink detection
            drink_boxes = object_detection_model.detect(frame)

            with context.detected_incompliance_lock:
                context.detected_incompliance.clear()

            if drink_boxes and len(drink_boxes) >= 1:
                # or (food_boxes and len(food_boxes) >= 1)):

                if datetime.now() - last_cleared >= timedelta(
                    hours=2
                ):  # Clear flagged ids every 2 hours
                    with context.flagged_foodbev_lock:
                        context.flagged_foodbev.clear()
                    last_cleared = datetime.now()

                # object detection pipeline
                with context.detected_incompliance_lock:
                    # Process drinks
                    for box in drink_boxes:
                        track_id = int(box.id) if box.id is not None else None
                        if track_id is None:
                            continue

                        cls_id = int(box.cls.cpu())
                        confidence = float(box.conf.cpu())
                        coords = box.xyxy[0].cpu().numpy()
                        # class_name = drink_model.names[cls_id]
                        # print(f"[Food/Drink] {class_name} (ID: {cls_id}) - {confidence:.2f}")

                        x1, y1, x2, y2 = map(int, coords)

                        cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 1)
                        cv.putText(
                            frame_copy,
                            f"id: {track_id}, conf: {confidence:.2f}",
                            (x1, y1 - 10),
                            cv.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255),
                            1,
                        )

                        if track_id not in context.flagged_foodbev:

                            # Check if it's a water bottle or not
                            object_crop = safe_crop(frame, x1, y1, x2, y2, padding=10)
                            predicted_label = classif_model.classify(object_crop)

                            # Discard saving coordinates if it's a water bottle (model tends to detect some bottles as milk can also)
                            # if predicted_label == "water_bottle" or predicted_label == "milk_can":
                            #     print("🚫 Water bottle, skipping")
                            #     continue

                            context.detected_incompliance[track_id] = [
                                coords,  # Coordinates of bbox
                                (
                                    (coords[0] + coords[2]) // 2,  # Center of bbox
                                    (coords[1] + coords[3]) // 2,
                                ),
                                confidence,  # Confidence score
                                cls_id,  # Class Id of detected object (refer to COCO dataset)
                            ]

                keypoints = pose_model.predict(frame)
                with context.pose_points_lock:
                    context.pose_points.clear()

                with context.detected_incompliance_lock and context.pose_points_lock:
                    # only process if theres both faces and food/beverages in frame
                    if context.detected_incompliance and (keypoints is not None):

                        context.pose_points = pose_model.parse_keypoints(keypoints)

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

    def stop(self):
        """
        Stops the worker thread and ensures that the processing thread is properly terminated.

        Waits for up to 2 seconds for the thread to stop gracefully.
        If the thread is still running, it is forcibly stopped.
        """
        self.running.clear()
        self.thread.join(timeout=2)
        print(f"[INFO] Detection worker {self.worker_id} stopped.")

    def submit(self, frame, camera):
        """
        Submits a new frame to the worker for processing.

        Parameters:
            frame (numpy.ndarray): The frame to be processed.
            camera (Camera): The camera context that provides necessary details for processing.
        """
        self.queue.put((frame, camera))
