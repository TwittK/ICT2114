import cv2 as cv
import psycopg2

class ProcessIncompliance:
  def __init__(self, db_params, camera_id):
    self.db_params = db_params
    self.camera_id = camera_id
    self.db = psycopg2.connect(**self.db_params)

  def get_date(self, current_date):
    return current_date[:10]

  # When face match is found in exisiting incompliance
  def match_found_new_incompliance(self, matches_found, nvr, local_detected_food_drinks, track_id, face_crop, current_date):

    # Get the matching person_id and the last incompliance date
    query = """ 
      SELECT p.PersonId, p.last_incompliance 
      FROM Snapshot AS s 
      JOIN Person p ON s.person_id = p.PersonId 
      WHERE s.snapshotId = %s;
    """
    # cursor = self.db.execute(query, (matches_found[1],))
    cursor = self.db.cursor()
    cursor.execute(query, (matches_found[1],))
    result = cursor.fetchone()

    if result:
      person_id, last_incompliance = result
      last_date = (last_incompliance[:10] if last_incompliance else None)

      # Current incompliance must happen on a different date
      today = self.get_date(current_date)
      if last_date != today and last_date is not None:

        face_crop = cv.resize(face_crop, (face_crop.shape[1] * 5, face_crop.shape[0] * 5,), cv.INTER_LINEAR)
        snapshot_id = nvr.insert_into_face_db(face_crop, person_id)

        if snapshot_id:
          print("[FACE] 🔴 Inserted face into library")
          update_query = """ 
            UPDATE Person 
            SET last_incompliance = %s, incompliance_count = incompliance_count + 1 
            WHERE PersonId = %s;
          """
          cursor.execute(update_query, (current_date, person_id))

          snapshot_query = """ 
            INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected, imageURL, person_id, camera_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s);
          """
          cursor.execute(
            snapshot_query,
            (
              snapshot_id,  # snapshot_id = PID from NVR (1 PID for every unique image)
              local_detected_food_drinks[track_id][2],  # confidence value
              current_date,
              str(local_detected_food_drinks[track_id][3]),  # detected object class id
              f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
              person_id,
              self.camera_id
            ),
          )
          self.db.commit()

          return person_id
        
        else:
          return None # Incompliance on the same date detected, skipping

    self.db.close()
    
    return None        
  
  # When NO face match is found in exisiting incompliance (a new person does incompliance)
  def no_match_new_incompliance(self, nvr, local_detected_food_drinks, track_id, face_crop, current_date):

    today = self.get_date(current_date)

    # Insert new record of a person into the database
    query = """ 
      INSERT INTO Person (last_incompliance, incompliance_count) 
      VALUES (%s, 1) 
      RETURNING PersonId;
    """
    cursor = self.db.cursor()
    cursor.execute(query, (current_date,))
    person_id = cursor.fetchone()[0]

    # Save face into NVR face library
    face_crop = cv.resize(face_crop, (face_crop.shape[1] * 5, face_crop.shape[0] * 5,), cv.INTER_LINEAR)
    snapshot_id = nvr.insert_into_face_db(face_crop, person_id)

    # Save incompliance snapshot and record details in database
    if snapshot_id:
      print("[FACE] 🔴 Inserted face into library")
      snapshot_query = """ 
        INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected, imageURL, person_id, camera_id) 
        VALUES (%s, %s, %s, %s, %s, %s, %s);
      """
      cursor.execute(
        snapshot_query,
        (
          snapshot_id,
          local_detected_food_drinks[track_id][2],  # confidence value
          current_date,
          str(local_detected_food_drinks[track_id][3]),  # detected object class id
          f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
          person_id,
          self.camera_id,  # temp camera id
        ),
      )
      self.db.commit()

    self.db.close()

    return person_id
  
  def close_connection(self):
    self.db.close()
