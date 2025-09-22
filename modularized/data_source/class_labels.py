# Filename: data_source/class_labels.py
class ClassLabelRepository:
    """
    Repository for mapping class IDs to human-readable labels.

    This class provides access to food and drink class labels from the COCO dataset.
    For more information, visit https://docs.ultralytics.com/datasets/detect/coco/#applications
    Supports retrieval of labels by class ID.

    Attributes:
        _class_id_to_label (dict): Internal mapping from class ID to label based on the COCO dataset.
    """
    def __init__(self):
        """Initializes the class ID to label mapping."""
        self._class_id_to_label = {
            39: "Bottle",
            40: "Wine Glass",
            41: "Cup",
            46: "Banana",
            47: "Apple",
            48: "Sandwich",
            49: "Orange",
            50: "broccoli",
            51: "Carrot",
            52: "Hot Dog",
            53: "Pizza",
            54: "Donut",
            55: "Cake"
        }

    def get_label(self, class_id: int) -> str:
        """
        Returns the human-readable label for a class ID

        Parameters:
            class_id (int): The ID of the class.

        Returns:
            str: The corresponding label if found, otherwise the string form of class_id.

        """
        return self._class_id_to_label.get(class_id, str(class_id))

    def get_all_labels(self) -> dict:
        """
        Returns a copy of the full class ID to label mapping.

        Returns:
            dict: A dictionary mapping all class IDs (int) to their corresponding human readable labels (str).

        """
        return self._class_id_to_label.copy()

    def get_food_class_ids(self) -> list:
        """
        Returns a list of all class IDs that are considered as food.

        Returns:
            list: A list of all class IDs (int) that are food.

        """
        return [46, 47, 48, 49, 50, 51, 52, 53, 54, 55]

    def get_drink_class_ids(self) -> list:
        """
        Returns a list of all class IDs that are considered as drinks.

        Returns:
            list: A list of all class IDs (int) that are drinks.

        """
        return [39, 40, 41]
