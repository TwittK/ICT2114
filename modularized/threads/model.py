from ultralytics import YOLO
import os

class BaseModel:
  """
  Base class for all model types.
  
  Attributes:
    model_name (str): Name or path of the YOLO model file. (.pt file)
  """
  def __init__(self, model_name):
    """
    Initializes the BaseModel with the given model name.
    
    Args:
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
  
class ImageClassificationModel(BaseModel):
  def __init__(self, model_name):
    super().__init__(model_name)

    self.model_instance = YOLO(os.path.join("yolo_models", self.model_name))

  def classify(self, frame):
    return self.get_model_instance(frame, verbose=False)

