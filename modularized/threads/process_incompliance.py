import cv2 as cv
import sqlite3

class ProcessIncompliance:
  def __init__(self, db_path):
    self.db_path = db_path
    self.db = sqlite3.connect(self.db_path)

  # When face match is found in exisiting incompliance
  def match_found_new_incompliance(self, matchesFound, nvr, local_detected_food_drinks, track_id, face_crop, current_date, today):

    # Get the matching person_id and the last incompliance date
    query = """ SELECT p.PersonId, p.last_incompliance FROM Snapshot AS s JOIN Person p ON s.person_id = p.PersonId WHERE s.snapshotId = ?;"""
    cursor = self.db.execute(query, (matchesFound[1],))
    result = cursor.fetchone()

    if result:
      person_id, last_incompliance = result
      last_date = (last_incompliance[:10] if last_incompliance else None)

      # Current incompliance must happen on a different date
      if last_date != today and last_date is not None:

        face_crop = cv.resize(face_crop, (face_crop.shape[1] * 5, face_crop.shape[0] * 5,), cv.INTER_LINEAR)
        snapshotId = nvr.insert_into_face_db(face_crop, person_id)

        if snapshotId:
          print("[FACE] 🔴 Inserted face into library")
          update_query = """ UPDATE Person SET last_incompliance = ?, incompliance_count = incompliance_count + 1 WHERE PersonId = ?; """
          self.db.execute(update_query, (current_date, person_id),)

          snapshot_query = """ INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected, imageURL, person_id, camera_id) VALUES (?, ?, ?, ?, ?, ?, ?)"""
          self.db.execute(
            snapshot_query,
            (
              snapshotId,  # snapshotId = PID from NVR (1 PID for every unique image)
              local_detected_food_drinks[track_id][2],  # confidence value
              current_date,
              str(local_detected_food_drinks[track_id][3]),  # detected object class id
              f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
              person_id,
              1,  # temp camera id
            ),
          )
          self.db.commit()

          return person_id
        
        else:
              return None # Incompliance on the same date detected, skipping

    return None        
  
  # When NO face match is found in exisiting incompliance (a new person does incompliance)
  def no_match_new_incompliance(self, nvr, local_detected_food_drinks, track_id, face_crop, current_date, today):

    # Insert new record of a person into the database
    query = " INSERT INTO Person (last_incompliance, incompliance_count) VALUES (?, 1) RETURNING PersonId; "
    cursor = self.db.execute(query, (current_date,))
    person_id = cursor.fetchone()[0]

    # Save face into NVR face library
    face_crop = cv.resize(face_crop, (face_crop.shape[1] * 5, face_crop.shape[0] * 5,), cv.INTER_LINEAR)
    #snapshotId = nvr.insert_into_face_db(face_crop, person_id)

    # Save incompliance snapshot and record details in database
    snapshotId = 1
    if snapshotId:
      print("[FACE] 🔴 Inserted face into library")
      snapshot_query = """ INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected, imageURL, person_id, camera_id) VALUES (?, ?, ?, ?, ?, ?, ?);"""
      self.db.execute(
        snapshot_query,
        (
          snapshotId,
          local_detected_food_drinks[track_id][2],  # confidence value
          current_date,
          str(local_detected_food_drinks[track_id][3]),  # detected object class id
          f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
          person_id,
          1,  # temp camera id
        ),
      )
      self.db.commit()

    return person_id
  
  def close_connection(self):
    self.db.close()
