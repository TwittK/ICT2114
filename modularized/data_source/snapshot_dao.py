# Filename: data_source/snapshot_dao.py
import psycopg2

class SnapshotDAO:
    """
    Data Access Object for snapshot records.

    This class wraps common database operations related to the Snapshot table.
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
            connection: A psycopg2 connection.
        """
        return psycopg2.connect(**self.db_params)

    def get_snapshot_by_id(self, snapshot_id):
        """
        Return the person and their last incompliance data using the snapshot id.

        Parameters:
            snapshot_id (int | str): The snapshotId to look up.

        Returns:
            tuple | None: (PersonId, last_incompliance) if found, else None.
        """
        query = """
            SELECT p.PersonId, p.last_incompliance
            FROM Snapshot AS s
                      JOIN Person p ON s.person_id = p.PersonId
            WHERE s.snapshotId = %s; \
            """
        with self._get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (str(snapshot_id),))
                result = cursor.fetchone()

                return result

    def insert_snapshot(
        self,
        snapshot_id,
        confidence,
        current_date,
        object_detected,
        image_url,
        person_id,
        camera_id,
    ):
        """
        Insert a new snapshot of an incompliance event.

        Parameters:
            snapshot_id (int | str): Unique identifier for the snapshot.
            confidence (float): Detection confidence value.
            current_date (str | datetime): Timestamp of the snapshot.
            object_detected (str | list): Object(s) detected in the snapshot.
            image_url (str): URL to the snapshot image.
            person_id (int): Associated person ID.
            camera_id (int): Associated camera ID.

        Returns:
            None
        """
        snapshot_query = """
                      INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected,
                                            imageURL, person_id, camera_id)
                      VALUES (%s, %s, %s, %s, %s, %s, %s); \
                      """
        with self._get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    snapshot_query,
                    (
                        snapshot_id,
                        confidence,
                        current_date,
                        str(object_detected),
                        image_url,
                        person_id,
                        camera_id,
                    ),
                )
                conn.commit()

    def get_latest_snapshots(self):
        """
        Retrieve the snapshots generated in the last 3 months.

        Returns:
            list[tuple]: List of (imageURL, time_generated) tuples ordered by time_generated descending.
        """
        query = "SELECT imageURL, time_generated FROM Snapshot WHERE time_generated > CURRENT_DATE - INTERVAL '3 months' ORDER BY time_generated DESC;"
        with self._get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()

                return results
