# Filename: data_source/camera_dao.py
import psycopg2
from psycopg2.extras import RealDictCursor
from database import create_camera, create_new_camera

from contextlib import contextmanager

LAB_NOT_FOUND = "Lab not found"


class CameraDAO:
    """
    Data Access Object for camera records.

    This class wraps common database operations related to cameras and
    labs. It is responsible for opening connections (using provided
    db_params), executing queries and returning structured results.

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

    @contextmanager
    def get_cursor(self):
        """Yield a cursor with an automatically-closed connection.

        The yielded cursor uses RealDictCursor so fetched rows are
        dict-like. The connection is committed after the context exits.

        Usage:
            with dao.get_cursor() as cursor:
                cursor.execute(...)
                results = cursor.fetchall()

        Yields:
            psycopg2 cursor: A cursor bound to an open connection.
        """
        conn = psycopg2.connect(**self.db_params, cursor_factory=RealDictCursor)
        try:
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _get_conn(self):
        """Open and return a new database connection.

        Returns:
            connection: A psycopg2 connection configured to return rows as dicts.
        """
        return psycopg2.connect(**self.db_params, cursor_factory=RealDictCursor)

    def get_lab_id(self, lab_name):
        """Return lab ID for a given lab name.

        Parameters:
            lab_name (str): The human-readable name of the lab.

        Returns:
            int | None: The LabId if the lab exists, otherwise None.
        """
        with self._get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT LabId FROM Lab WHERE lab_name = %s", (lab_name,))
                row = cursor.fetchone()
                return row["labid"] if row else None

    def count_cameras_in_lab(self, lab_id):
        """Return number of cameras associated with a lab.

        Parameters:
            lab_id (int): The LabId to count cameras for.

        Returns:
            int: The number of Camera rows that reference the given lab.
        """
        with self._get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM Camera WHERE camera_lab_id = %s",
                    (lab_id,),
                )
                return cursor.fetchone()["count"]

    def add_default_camera(self, lab_name, user_id):
        """Create a camera with a default name inside a lab.

        The default name is generated as "Camera {n}" where n is the
        number of existing cameras in the lab plus one.

        Parameters:
            lab_name (str): The name of the lab to add the camera to.
            user_id (int): The user id who owns the created camera.

        Returns:
            tuple(bool, str): (success, message). On success the message
            describes the camera added; on failure the message explains why.
        """
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, LAB_NOT_FOUND

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
        """Delete a camera by its name, lab name, and user ID.

        Parameters:
            lab_name (str): Name of the lab the camera belongs to.
            camera_name (str): The name of the camera to delete.
            user_id (int): The id of the user who owns the camera.

        Returns:
            tuple(bool, str): (success, message). Success indicates whether a
            row was removed. Message contains a human readable result.
        """
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, LAB_NOT_FOUND

        with self._get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE
                    FROM Camera
                    WHERE name = %s
                      AND camera_lab_id = %s
                      AND camera_user_id = %s
                    """,
                    (camera_name, lab_id, user_id),
                )
                affected_rows = cursor.rowcount
                conn.commit()

        if affected_rows > 0:
            return True, f"Camera '{camera_name}' deleted successfully."
        else:
            return False, f"Failed to delete camera '{camera_name}'."

    def get_camera_id(self, lab_name, camera_name, user_id):
        """Get a camera id by its name, lab name, and user ID.

        Parameters:
            lab_name (str): The lab name to search in.
            camera_name (str): The camera name to search for.
            user_id (int): The camera owner id.

        Returns:
            tuple(bool, int | None): (found, camera_id). If the lab is not
            found returns (False, None). If the camera does not exist returns
            (False, None). On success returns (True, camera_id).
        """
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, None  # Lab not found

        with self._get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT CameraId
                    FROM Camera
                    WHERE name = %s
                      AND camera_lab_id = %s
                      AND camera_user_id = %s
                    """,
                    (camera_name, lab_id, user_id),
                )

                row = cursor.fetchone()
                if row is None:
                    return False, None

                return True, row["cameraid"]

    def add_new_camera(self, lab_name, user_id, device_info):
        """Create a new camera record with extended device information.

        Parameters:
            lab_name (str): The lab to create the camera in.
            user_id (int): The owner of the camera.
            device_info (dict): Device properties expected to contain keys:
                resolution, frame_rate, encoding, camera_ip_type, ip_address,
                subnet_mask, gateway, timezone, sync_with_ntp,
                ntp_server_address, time

        Returns:
            tuple(int | None, str): On success returns (camera_id, message).
            On failure returns (None, error_message).
        """
        lab_id = self.get_lab_id(lab_name)
        if lab_id is None:
            return False, LAB_NOT_FOUND

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
            time=device_info["time"],
        )

        if success:
            return (
                camera_id,
                f"{default_name} added to {lab_name} as CameraId {camera_id}",
            )
        else:
            return None, "Failed to add camera"

    def get_cameras_by_lab(self, lab_name):
        """Return all camera names in a given lab.

        Parameters:
            lab_name (str): Lab name to query.

        Returns:
            list[str]: Ordered list of camera names for the lab. Empty list if none.
        """
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT c.name
                FROM Camera c
                         JOIN Lab l ON c.camera_lab_id = l.LabId
                WHERE l.lab_name = %s
                ORDER BY c.name
                """,
                (lab_name,),
            )
            return [row["name"] for row in cursor.fetchall()]

    def get_first_cameras_for_lab(self, lab_name):
        """
        Returns the name of the first camera for a given lab,
        or None if no camera exists.

        Parameters:
            lab_name (str): The lab name to query. If falsy, None is returned.

        Returns:
            str | None: The name of the first camera ordered by name, or None.
        """
        if not lab_name:
            return None

        with self.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT c.name
                FROM Camera c
                         JOIN Lab l ON c.camera_lab_id = l.LabId
                WHERE l.lab_name = %s
                ORDER BY c.name LIMIT 1
                """, (lab_name,),
            )
            row = cursor.fetchone()
            return row["name"] if row else None
