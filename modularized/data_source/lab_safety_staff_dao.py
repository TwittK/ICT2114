import psycopg2
from psycopg2.extras import RealDictCursor


class LabSafetyStaffDAO:
    def __init__(self, db_params):
        self.db_params = db_params

    def _get_conn(self):
        """Helper to open a connection with dict-style rows."""
        return psycopg2.connect(**self.db_params, cursor_factory=RealDictCursor)

    def get_email_by_camera_id(self, camera_id):
        """
        Retrieve the lab safety email associated with a given camera ID.
        Returns None if no email is found.
        """
        query = """
            SELECT lss.lab_safety_email
            FROM Camera c
            JOIN Lab l ON c.camera_lab_id = l.LabId
            JOIN LabSafetyStaff lss ON lss.lab_id = l.LabId
            WHERE c.CameraId = %s
            AND lss.lab_safety_email IS NOT NULL;        
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(query, (camera_id,))
                result = cursor.fetchone()
                return result[0] if result else None
        except psycopg2.Error as e:
            print(f"Error fetching email for camera {camera_id}: {e}")
            return None
