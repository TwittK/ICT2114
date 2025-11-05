import csv
from pathlib import Path
from ultralytics import YOLO
from tqdm import tqdm

# --- Configuration ---
DATASET_ROOT = Path("datasets")
MODEL_PATH = Path("yolo_models/yolov8n-cls.pt")
OUTPUT_CSV = "accuracy_results.csv"
# --- End Configuration ---

def test_accuracy():
    """
    Tests the accuracy of a YOLO classification model against a structured dataset.
    """
    # 1. Load the YOLO model
    if not MODEL_PATH.exists():
        print(f"Error: Model not found at {MODEL_PATH}")
        return
    model = YOLO(MODEL_PATH)
    print(f"Model '{MODEL_PATH}' loaded successfully.")
    print(f"Class names: {model.names}")

    # 2. Find all image files in the dataset directory
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
    image_paths = [p for p in DATASET_ROOT.rglob("*") if p.suffix.lower() in image_extensions]

    if not image_paths:
        print(f"Error: No images found in {DATASET_ROOT}")
        return

    print(f"Found {len(image_paths)} images to test.")

    # 3. Prepare CSV for logging results
    correct_predictions = 0
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Write header
        writer.writerow(["image_path", "ground_truth", "predicted_label", "confidence", "is_correct"])

        # 4. Iterate through each image, predict, and log
        for image_path in tqdm(image_paths, desc="Processing images"):
            # The ground truth is the name of the parent directory of the tiles folder (e.g., 'no_bottle')
            ground_truth = image_path.parent.parent.name

            # Run prediction
            results = model(image_path, verbose=False) # verbose=False to prevent console spam
            
            if not results:
                continue

            # Get top prediction from the classifier
            result = results[0]
            top1_pred_index = result.probs.top1
            top1_confidence = result.probs.top1conf.item()
            predicted_label = model.names[top1_pred_index]

            # Compare prediction with ground truth
            is_correct = (ground_truth == predicted_label)
            if is_correct:
                correct_predictions += 1

            # Log the result to the CSV file
            writer.writerow([
                str(image_path),
                ground_truth,
                predicted_label,
                f"{top1_confidence:.4f}",
                is_correct
            ])

    # 5. Calculate and display final accuracy
    total_images = len(image_paths)
    accuracy = (correct_predictions / total_images) * 100 if total_images > 0 else 0

    print("\n--- Accuracy Test Complete ---")
    print(f"Total Images Tested: {total_images}")
    print(f"Correct Predictions: {correct_predictions}")
    print(f"Overall Accuracy: {accuracy:.2f}%")
    print(f"Results have been saved to '{OUTPUT_CSV}'")

if __name__ == "__main__":
    test_accuracy()