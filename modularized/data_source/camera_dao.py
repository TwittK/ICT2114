import sqlite3
from database import create_camera, create_new_camera


class CameraDAO:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_lab_id(self, lab_name):
        """Return lab ID for a given lab name."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT LabId FROM Lab WHERE lab_name = ?", (lab_name,))
            row = cursor.fetchone()
            return row[0] if row else None

    def count_cameras_in_lab(self, lab_id):
        """Return number of cameras in a given lab."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Camera WHERE camera_lab_id = ?", (lab_id,))
            return cursor.fetchone()[0]

    def add_default_camera(self, lab_name, user_id):
        """Creates a default-named camera in a given lab."""
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, "Lab not found"

        count = self.count_cameras_in_lab(lab_id)
        default_name = f"Camera {count + 1}"

        success = create_camera(
            name=default_name,
            camera_user_id=user_id,
            camera_lab_id=lab_id,
        )

        if success:
            return True, f"{default_name} added to {lab_name}"
        else:
            return False, "Failed to add camera"

    def delete_camera(self, lab_name, camera_name, user_id):
        """Delete a camera by its name, lab name, and user ID."""
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, "Lab not found"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           DELETE
                           FROM Camera
                           WHERE name = ?
                             AND camera_lab_id = ?
                             AND camera_user_id = ?
                           """, (camera_name, lab_id, user_id))
            conn.commit()
            affected_rows = cursor.rowcount

        if affected_rows > 0:
            return True, f"Camera '{camera_name}' deleted successfully."
        else:
            return False, f"Failed to delete camera '{camera_name}'."

    def get_camera_id(self, lab_name, camera_name, user_id):
        """Get a camera id by its name, lab name, and user ID."""
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, None # Lab not found

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT CameraId FROM Camera WHERE name = ? AND camera_lab_id = ? AND camera_user_id = ?", (camera_name, lab_id, user_id))

            row = cursor.fetchone()
            if row is None:
                return False, None

            return True, row[0]
    
    def add_new_camera(self, lab_name, user_id, device_info):
        """Creates a default-named camera in a given lab."""
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, "Lab not found"

        count = self.count_cameras_in_lab(lab_id)
        default_name = f"Camera {count + 1}"

        success, camera_id = create_new_camera(
            name=default_name,
            camera_user_id=user_id,
            camera_lab_id=lab_id,
            resolution=device_info["resolution"],
            frame_rate=device_info["frame_rate"],
            encoding=device_info["encoding"],
            camera_ip_type=device_info["camera_ip_type"],
            ip_address=device_info["ip_address"],
            subnet_mask=device_info["subnet_mask"],
            gateway=device_info["gateway"],
            timezone=device_info["timezone"],
            sync_with_ntp=device_info["sync_with_ntp"],
            ntp_server_address=device_info["ntp_server_address"],
            time=device_info["time"]
        )

        if success:
            return camera_id, f"{default_name} added to {lab_name} as CameraId {camera_id}"
        else:
            return None, "Failed to add camera"