from shared.camera import Camera
from concurrent.futures import ThreadPoolExecutor
import cv2 as cv
import torch

class CollaborativeInference:
  def __init__(self, context: Camera, model_list, min_model_votes):
    self.context = context
    self.model_list = model_list
    self.min_model_votes = min_model_votes

  def run_model_detection(self, model, frame, target_classes_id, conf_threshold, gpu_id):
    
    device_str = f"cuda:{gpu_id}" if gpu_id is not None else "cpu"
    # Main food/ drink object detection
    result = model.track(
        frame,
        persist=True,
        classes=target_classes_id,
        conf=conf_threshold,
        verbose=False,
        device=torch.device('cpu' if gpu_id == None else gpu_id) 
    )
    boxes = result[0].boxes
    return boxes

  def compute_iou(self, box1, box2):
    """
    Computes the Intersection over Union (IoU) between two bounding boxes with this formula: IoU = Area of intersection / Area of union

    Parameters:
      box1 (list or tuple): Bounding box in the format [x1, y1, x2, y2], where (x1, y1) is the top-left corner and (x2, y2) is the bottom-right corner.
      box2 (list or tuple): Bounding box in the format [x1, y1, x2, y2].

    Returns:
      float: IoU value in the range [0, 1]. Returns 0 if boxes do not overlap.
    """
    # Intersection coords
    inter_x1 = torch.max(box1[0], box2[0])
    inter_y1 = torch.max(box1[1], box2[1])
    inter_x2 = torch.min(box1[2], box2[2])
    inter_y2 = torch.min(box1[3], box2[3])

    # Clamping, so that no negative areas
    inter_area = (inter_x2 - inter_x1).clamp(min=0) * (inter_y2 - inter_y1).clamp(min=0)

    # Calculate the total union area of the boxes
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = area1 + area2 - inter_area

    return inter_area / union_area if union_area > 0 else torch.tensor(0.0, device=box1.device)

  def match_objects(self, model_results, iou_threshold=0.9):
    """
    Given the detection results from each model, match and group objects that refer 
    to the same real-world entity based on Intersection over Union (IoU).

    Parameters:
      model_results (list)

    Returns:
      A list that contains matched detections from different models 
      that are identified as the same object. 
      For example:
      [
        [object1_from_model1, object1_from_model2],
        [object2_from_model1, object2_from_model3],
        ...
      ] 
    """

    # Flatten all detections
    all_detections = []
    
    for model_idx, model_boxes in enumerate(model_results):
      for i in range(len(model_boxes)):
        all_detections.append({
            'model_idx': model_idx,
            'box_idx': i,
            'box': model_boxes.xyxy[i],  # GPU tensor
            'cls': model_boxes.cls[i],   # GPU tensor
            'conf': model_boxes.conf[i], # GPU tensor
            'track_id': model_boxes.id[i] if model_boxes.id is not None else None,
            'boxes_obj': model_boxes
        })

    # Match all detection across different models
    matched = []
    used = set()

    for i, detection1 in enumerate(all_detections):
      if i in used:
        continue

      group = [detection1]
      used.add(i)

      # Compare every detection against every other detection
      for j, detection2 in enumerate(all_detections):
          if j in used or (detection1['model_idx'] == detection2['model_idx'] and len(all_detections) != 1):
            continue

          # Class different, so not the same object
          if detection1['cls'] != detection2['cls']:
            continue
          
          iou = self.compute_iou(detection1['box'], detection2['box'])

          if iou > iou_threshold:
            group.append(detection2)
            used.add(j)

      if len(group) > 1 or len(all_detections) == 1:
        # Only return groups that include multiple detections
        matched.append([d['boxes_obj'][d['box_idx']] for d in group])

    return matched

  def calculate_avg_confidence(self, matched_objects, avg_conf_threshold):
    
    filtered = []
    filtered_confidence = []
    filtered_boxes = []
    for object_group in matched_objects:
      avg_conf = sum(obj.conf.item() for obj in object_group) / len(object_group)
      if avg_conf >= avg_conf_threshold:

        # Merge bounding boxes
        x1 = min(obj.xyxy[0][0].item() for obj in object_group)
        y1 = min(obj.xyxy[0][1].item() for obj in object_group)
        x2 = max(obj.xyxy[0][2].item() for obj in object_group)
        y2 = max(obj.xyxy[0][3].item() for obj in object_group)
        
        merged_box = [x1, y1, x2, y2]

        filtered.append(object_group)
        filtered_confidence.append(avg_conf)
        filtered_boxes.append(merged_box)

    return filtered, filtered_confidence, filtered_boxes
  
  def collaborative_inference(self, frame):
    model_results = []
    with self.context.manager.inference_lock:
      with ThreadPoolExecutor(max_workers=len(self.model_list)) as executor:
        futures = []
        for model in self.model_list:
          futures.append(
            executor.submit(self.run_model_detection, model.get_model_instance(), frame, model.get_target_classes_id(), model.get_conf_threshold(), model.get_gpu_device())
          )

        for future in futures:
          # Add to results if theres at least 1 element in the tensor (one detection found)
          if future.result().cls.numel() > 0:
            model_results.append(future.result())

    return model_results
  
  def process_inference_results(self, frame_copy, model_results, avg_conf_threshold):

    # Only proceed if at least min_model_votes models detected food/ drinks.
    if len(model_results) >= self.min_model_votes:

      # Unpack inference results for each model.
      for model in model_results:
        for box in model:
          track_id = int(box.id) if box.id is not None else None
          if (track_id is None):
            continue

          cls_id = int(box.cls.cpu())
          confidence = float(box.conf.cpu())
          coords = box.xyxy[0].cpu().numpy()
          # print(cls_id, confidence, coords, model)

          x1, y1, x2, y2 = map(int, coords)

          # Display bounding box on dashboard video feed.
          cv.rectangle(frame_copy, (x1, y1), (x2, y2), (0, 0, 255), 2)
          cv.putText(frame_copy, f"id: {track_id}, conf: {confidence:.2f}", (x1, y1 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)


      # print(model_results)
      matched_objects = self.match_objects(model_results)

      # print(f"Matched count: {len(matched_objects)}")
      if matched_objects:

        filtered_obj_group, filtered_confidence, filtered_boxes = self.calculate_avg_confidence(matched_objects, avg_conf_threshold)

        for i in range(len(filtered_obj_group)):
          print(f"Average confidence of object {i}: {filtered_confidence[i]:2f}, at {filtered_boxes[i]}")

        return filtered_obj_group, filtered_confidence, filtered_boxes
    
    return None, None, None
    