import os

class BaseModel:
  """
  Base class for all model types.
  """
  def __init__(self, model_path):
    """
    Initializes the BaseModel with the given model name.
    
    Parameters:
      model_path (str): Path of model file.
    """
    self.model_path = model_path

class ObjectDetectionModel(BaseModel):
  def __init__(self, model_path, target_classes_id, conf_threshold, gpu_device=None):
    super().__init__(model_path)

    self.target_classes_id = target_classes_id
    self.conf_threshold = conf_threshold
    self.gpu_device = gpu_device

class PoseDetectionModel(BaseModel):
  def __init__(self, model_path, conf_threshold, iou):
    super().__init__(model_path)

    self.iou = iou
    self.conf_threshold = conf_threshold
  
  # def predict(self, frame):
  #   pose_results = self.model_instance.predict(frame, conf=self.conf_threshold, iou=self.iou, verbose=False)[0]
  #   keypoints = pose_results.keypoints.xy if pose_results.keypoints else []

  #   return keypoints
  
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
  def __init__(self, model_path):
    super().__init__(model_path)

  # def classify(self, frame):
  #   model = self.get_model_instance()

  #   # Run inference on classification model and extract predicted label
  #   results = model(frame, verbose=False)
  #   pred = results[0]
  #   label = pred.names[pred.probs.top1]

  #   return label
