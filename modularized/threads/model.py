from ultralytics import YOLO
import os

class BaseModel:
  """
  Base class for all model types.
  """
  def __init__(self, model_name):
    """
    Initializes the BaseModel with the given model name.
    
    Parameters:
      model_name (str): Name (not the path) of model file. (.pt file)
    """
    self.model_name = model_name

  def get_model_instance(self):
    """
    Returns the model instance.
    
    Returns:
      model_instance: The loaded YOLO model instance.
    """
    return self.model_instance


class ObjectDetectionModel(BaseModel):
  def __init__(self, model_name, target_classes_id, conf_threshold, gpu_device=None):
    super().__init__(model_name)

    self.target_classes_id = target_classes_id
    self.conf_threshold = conf_threshold
    self.gpu_device = gpu_device
    self.model_instance = YOLO(os.path.join("yolo_models", self.model_name))

  def get_gpu_device(self):
    return self.gpu_device
  
  def get_target_classes_id(self):
    return self.target_classes_id
  
  def get_conf_threshold(self):
    return self.conf_threshold


class PoseDetectionModel(BaseModel):
  def __init__(self, model_name, conf_threshold, iou):
    super().__init__(model_name)

    self.iou = iou
    self.conf_threshold = conf_threshold
    self.model_instance = YOLO(os.path.join("yolo_models", self.model_name))

  def get_conf_threshold(self):
    return self.conf_threshold
  
  def predict(self, frame):
    pose_results = self.model_instance.predict(frame, conf=self.conf_threshold, iou=self.iou, verbose=False)[0]
    keypoints = pose_results.keypoints.xy if pose_results.keypoints else []

    return keypoints
  
  def parse_keypoints(self, keypoints):
    # Save landmarks for each person
    results = []
    for person in keypoints:
      try:
        person_lm = person.cpu().numpy()
        results.append({
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
      
    return results

class ImageClassificationModel(BaseModel):
  def __init__(self, model_name):
    super().__init__(model_name)

    self.model_instance = YOLO(os.path.join("yolo_models", self.model_name))

  def classify(self, frame):
    model = self.get_model_instance()

    # Run inference on classification model and extract predicted label
    results = model(frame, verbose=False)
    pred = results[0]
    label = pred.names[pred.probs.top1]

    return label

