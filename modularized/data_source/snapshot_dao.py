import psycopg2

class SnapshotDAO:
  def __init__(self, db_params):
    self.db_params = db_params

  def _get_conn(self):
    """Helper to open a new connection."""
    return psycopg2.connect(**self.db_params)

  def get_snapshot_by_id(self, snapshot_id):
    """Return the person and their last incompliance data using the snapshot id."""
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
      
  def insert_snapshot(self, snapshot_id, confidence, current_date, object_detected, image_url, person_id, camera_id):
    """Insert a new snapshot of an incompliance."""
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
            camera_id
          ),
        )
        conn.commit()