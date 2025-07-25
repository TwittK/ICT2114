# Filename: data_source/class_labels.py
class ClassLabelRepository:
    def __init__(self):
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
        """Returns the human-readable label for a class ID"""
        return self._class_id_to_label.get(class_id, str(class_id))

    def get_all_labels(self) -> dict:
        """Returns a copy of the full class ID to label mapping."""
        return self._class_id_to_label.copy()

    def get_food_class_ids(self) -> list:
        return [46, 47, 48, 49, 50, 51, 52, 53, 54, 55]

    def get_drink_class_ids(self) -> list:
        return [39, 40, 41]
