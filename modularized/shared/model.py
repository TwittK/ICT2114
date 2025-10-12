import os, torch
from ultralytics import YOLO

class BaseModel:
  """
  Base class for all model types.
  """
  def __init__(self, model):
    """
    Initializes the BaseModel with the given model name.
    
    Parameters:
      model (str): Name of the YOLO model file (.pt) to load.
    """
    self.model = YOLO(os.path.join("yolo_models", model))

class ObjectDetectionModel(BaseModel):
  def __init__(self, model, gpu_device=None):
    """
    Initializes the ObjectDetectionModel.

    Parameters:
      model (str): Model file name (.pt) to load from 'yolo_models' directory.
      gpu_device (int, optional): Index of the GPU to use. If None, uses CPU.
    """
    super().__init__(model)
    self.gpu_device = gpu_device

  def detect(self, frame):
    """
    Runs object detection on a given frame.

    Parameters:
      frame (numpy.ndarray): Input frame for detection.

    Returns:
      Boxes: Detected bounding boxes of target classes.
    """
    device_str = f"cuda:{self.gpu_device}" if self.gpu_device is not None else "cpu"
    self.model.to(torch.device(device_str))
    result = self.model.track(
      frame,
      persist=True,
      classes=[39, 40, 41, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55],
      conf=0.3,
      verbose=False
    )
    drink_boxes = result[0].boxes
    return drink_boxes

class PoseDetectionModel(BaseModel):
  """
  YOLO pose detection model for estimating keypoints on human figures.
  """
  def __init__(self, model, conf_threshold, iou):
    """
    Initializes the PoseDetectionModel.

    Parameters:
      model (str): Name of the YOLO pose model file (.pt)
      conf_threshold (float): Minimum confidence score for valid predictions.
      iou (float): IoU threshold for non-maximum suppression.
    """
    super().__init__(model)

    self.iou = iou
    self.conf_threshold = conf_threshold
    
  def predict(self, frame):
    """
    Performs pose prediction (keypoint estimation) on an frame.

    Parameters:
      frame (numpy.ndarray): Input image for pose detection.

    Returns:
      None or torch.Tensor: Keypoints for each detected person, or None if none found.
    """
    pose_results = self.model.predict(frame, conf=self.conf_threshold, iou=self.iou, verbose=False)[0]
    keypoints = pose_results.keypoints.xy if pose_results.keypoints else None

    return keypoints
  
  def parse_keypoints(self, keypoints):
    """
    Parses raw keypoints into a dictionary of named landmarks for each person.

    Parameters:
      keypoints (torch.Tensor): Keypoints from the pose model.

    Returns:
      list of dict: Each dict contains named keypoint positions (e.g., nose, wrists, eyes).
    """
    results = []
    for person in keypoints:
      try:
        person_lm = person.cpu().numpy()
        landmarks = {
          "nose": person_lm[0],
          "left_wrist": person_lm[9],
          "right_wrist": person_lm[10],
          "left_ear": person_lm[3],
          "right_ear": person_lm[4],
          "left_eye": person_lm[1],
          "right_eye": person_lm[2],
        }
        results.append(landmarks)
      except Exception:
        continue
      
    return results

class ImageClassificationModel(BaseModel):
  """
  YOLO image classification model.
  """
  def __init__(self, model):
    super().__init__(model)

  def classify(self, frame):
    """
    Classifies an image and returns the top predicted label.

    Parameters:
      frame (numpy.ndarray): Input image for classification.

    Returns:
      str: The name of the predicted class label.
    """
    results = self.model(frame, verbose=False)
    pred = results[0]
    label = pred.names[pred.probs.top1]

    return label
