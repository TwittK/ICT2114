# Filename: data_source/lab_safety_staff_dao.py
import psycopg2
from psycopg2.extras import RealDictCursor


class LabSafetyStaffDAO:
    """
    Data Access Object for lab safety staff records.

    This class wraps common database operations related to lab safety staff.
    It is responsible for opening connections (using provided db_params),
    executing queries, and returning structured results.

    Attributes:
        db_params (dict): Keyword arguments passed to psycopg2.connect()
            to establish a database connection (host, port, user, password,
            database, etc.).
    """

    def __init__(self, db_params):
        """Initialise the DAO with database connection parameters.

        Parameters:
            db_params (dict): Parameters forwarded to psycopg2.connect().
        """
        self.db_params = db_params

    def _get_conn(self):
        """Open and return a new database connection.

        Returns:
            connection: A psycopg2 connection configured to return rows as dicts.
        """
        return psycopg2.connect(**self.db_params, cursor_factory=RealDictCursor)

    def get_email_by_camera_id(self, camera_id):
        """
        Retrieve the lab safety email(s) associated with a given camera ID.

        Parameters:
            camera_id (int): The CameraId to look up.

        Returns:
            list[dict] | None: List of dicts with lab_safety_email, or None if not found or on error.
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
                result = cursor.fetchall()
                return result if result else None
        except psycopg2.Error as e:
            print(f"Error fetching email for camera {camera_id}: {e}")
            return None
