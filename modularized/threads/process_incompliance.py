import cv2 as cv
from data_source.snapshot_dao import SnapshotDAO
from data_source.person_dao import PersonDAO

class ProcessIncompliance:
    """
    Handles processing of food/ drink incompliance detections.
    
    Interacts with DAOs to store new snapshots, and update person records.
    Also manages face data in the NVR face database.
    """

    def __init__(self, db_params, camera_id):
        """
        Initialize the ProcessIncompliance handler.

        Parameters:
            db_params (dict): Database connection parameters.
            camera_id (int): Identifier for the camera used for detection.
        """
        self.db_params = db_params
        self.camera_id = camera_id
        self.snapshot_dao = SnapshotDAO(db_params)
        self.person_dao = PersonDAO(db_params)

    def _get_date(self, current_date):
        """
        Extract date (YYYY-MM-DD) from the last 10 characters in a timestamp string.

        Parameters:
            current_date (str): The timestamp.

        Returns:
            str: Date in 'YYYY-MM-DD' format.
        """
        return str(current_date)[:10]

    def match_found_new_incompliance(self, matches_found, nvr, local_detected_food_drinks, track_id, face_crop, current_date):
        """
        Handle a case where a face match is found in the existing incompliance records.

        Parameters:
            matches_found (tuple): Tuple containing match status and snapshot ID.
            nvr (NVR): NVR object for NVR face database operations.
            local_detected_food_drinks (dict): Detection results containing confidence and class ID.
            track_id (int): Identifier for the tracked food/ drink.
            face_crop (numpy.ndarray): Cropped face image.
            current_date (str): Timestamp of the detection.

        Returns:
            int or None: Person ID if a previous snapshot is found and the last incompliance is on a different date.
        """
        # Find previous record of the incompliance
        result = self.snapshot_dao.get_snapshot_by_id(matches_found[1])

        if result:
            person_id, last_incompliance = result
            last_date = (str(last_incompliance)[:10] if last_incompliance else None)

            # Current incompliance must happen on a different date
            today = self._get_date(current_date)
            if last_date != today and last_date is not None:

                face_crop = cv.resize(face_crop, (face_crop.shape[1] * 5, face_crop.shape[0] * 5,), cv.INTER_LINEAR)
                snapshot_id = nvr.insert_into_face_db(face_crop, person_id)

                if snapshot_id:
                    print("[INFO] 🔴 Inserted face into NVR Face Database")

                    # Update the incompliance details and save snapshot under the same person id
                    self.person_dao.update_last_incompliance(person_id, current_date)
                    self.snapshot_dao.insert_snapshot(
                        str(snapshot_id),
                        local_detected_food_drinks[track_id][2], # confidence value
                        current_date,
                        str(local_detected_food_drinks[track_id][3]),  # detected object class id
                        f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
                        person_id,
                        self.camera_id
                    )
                    updated_count = self.person_dao.get_incompliance_count(person_id)

                    # Send email only on second and subsequent incompliances
                    if updated_count >= 2:
                        return person_id
                    else:
                        return None
            else:
                return None  # Incompliance on the same date detected, skipping

        return None

    def no_match_new_incompliance(self, nvr, local_detected_food_drinks, track_id, face_crop, current_date):
        """
        Handle a case where no face match is found. (A new person committing incompliance)

        Parameters:
            nvr (NVR): NVR object for NVR face database operations.
            local_detected_food_drinks (dict): Detection results containing confidence and class ID.
            track_id (int): Identifier for the tracked food/ drink.
            face_crop (numpy.ndarray): Cropped face image.
            current_date (str): Timestamp of the detection.

        Returns:
            int: The new person's ID after insertion.
        """
        today = self._get_date(current_date)
        person_id = self.person_dao.insert_new_person(current_date)

        # Save face into NVR face library
        face_crop = cv.resize(face_crop, (face_crop.shape[1] * 5, face_crop.shape[0] * 5,), cv.INTER_LINEAR)
        snapshot_id = nvr.insert_into_face_db(face_crop, person_id)

        # Save incompliance snapshot and record details under a new person in database
        if snapshot_id:
            print("[INFO] 🔴 Inserted face into NVR Face Database")
            self.snapshot_dao.insert_snapshot(
                str(snapshot_id),
                local_detected_food_drinks[track_id][2], # confidence value
                current_date,
                str(local_detected_food_drinks[track_id][3]),  # detected object class id
                f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
                person_id,
                self.camera_id
            )
        return person_id

