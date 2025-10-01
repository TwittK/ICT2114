import psycopg2

class SnapshotDAO:
  def __init__(self, db_params):
    self.db_params = db_params

  def _get_conn(self):
    """Helper to open a new connection."""
    return psycopg2.connect(**self.db_params)
  
  def get_snapshot_by_snapshot_id(self, snapshot_id):
    # Get the matching person_id and the last incompliance date
    with self._get_conn() as conn:
      with conn.cursor() as cursor:
        query = """ 
          SELECT p.PersonId, p.last_incompliance 
          FROM Snapshot AS s 
          JOIN Person p ON s.person_id = p.PersonId 
          WHERE s.snapshotId = %s;
        """
        cursor.execute(query, (snapshot_id,))
        result = cursor.fetchone()

    return result


  def insert_new_incompliance(self, snapshot_id, confidence, time_generated, object_detected, image_path, person_id, camera_id):
    with self._get_conn() as conn:
      with conn.cursor() as cursor: 
        snapshot_query = """ 
          INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected, imageURL, person_id, camera_id) 
          VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        cursor.execute(
          snapshot_query,
          (
            snapshot_id,  # snapshot_id refers to the PID from NVR (1 PID for every unique image)
            confidence,
            time_generated,
            object_detected, # detected object class id
            image_path,
            person_id,
            camera_id
          ),
        )
        conn.commit()