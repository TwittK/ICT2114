import sqlite3
import queue, time, os
import numpy as np
from datetime import datetime
from threads.saver import save_img
from shared.state import (
    process_queue,
    running,
    detected_incompliance_lock,
    pose_points_lock,
    pose_points,
    detected_incompliance,
    flagged_foodbev_lock,
    flagged_foodbev,
    wrist_proximity_history,
)
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import uuid
import time
import cv2 as cv
from io import BytesIO

# Constants
NOSE_THRESHOLD = 250  # Distance thresholds
WRIST_THRESHOLD = 100
REQUIRED_DURATION = 2.0  # seconds
REQUIRED_COUNT = 3  # number of detections in that duration
FACE_DISTANCE_THRESHOLD = 10

INCOMPLIANCES_FDID = "D3FB23C8155040E4BE08374A418ED0CA"
NVR_IP = "192.168.1.63"


def get_mode_data(frame):
    url = f"http://{NVR_IP}/ISAPI/Intelligent/analysisImage/face"

    success, encoded_image = cv.imencode(".jpg", frame)
    if not success:
        print("❌ Failed to encode frame")
        return None

    image_data = encoded_image.tobytes()

    # Set headers
    headers = {"Content-Type": "application/octet-stream"}

    response = requests.post(
        url, data=image_data, headers=headers, auth=HTTPDigestAuth("admin", "Sit12345")
    )
    print("Status Code:", response.status_code)
    if response.ok:
        # print("Response Body:\n", response.text)

        ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}

        try:
            root = ET.fromstring(response.text)

            # Find modeData using the namespace
            mode_data_elem = root.find(".//isapi:modeData", namespaces=ns)

            if mode_data_elem is not None:
                # print("✅ modeData found:\n", mode_data_elem.text)
                modeData = mode_data_elem.text
            else:
                print("❌ modeData not found.")
                return None

        except ET.ParseError as e:
            print("❌ XML parsing error:", e)
            return None
    else:
        print("❌ Request failed:", response.status_code, response.reason)
        return None

    return modeData


def get_face_comparison(modeData, FDID):
    if modeData is not None:
        randomUUID = uuid.uuid4()

        # Build the XML payload
        xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
        <FDSearchDescription>
            <FDID>{FDID}</FDID>
            <OccurrencesInfo>
                <enabled>true</enabled>
                <occurrences>0</occurrences>
                <occurrencesSearchType>greaterThanOrEqual</occurrencesSearchType>
            </OccurrencesInfo>
            <FaceModeList>
                <FaceMode>
                    <ModeInfo>
                        <similarity>80</similarity>
                        <modeData>{modeData}</modeData>
                    </ModeInfo>
                </FaceMode>
            </FaceModeList>
            <searchID>{randomUUID}</searchID>
            <maxResults>1</maxResults>
            <searchResultPosition>0</searchResultPosition>
        </FDSearchDescription>
        """

        # Set headers
        headers = {"Content-Type": "application/xml"}

        # Send the POST request
        response = requests.post(
            "http://{NVR_IP}/ISAPI/Intelligent/FDLib/FDSearch?security=1&iv=6e130e2ec9c415ed9b8dd80e732b9d82",
            data=xml_payload.encode("utf-8"),
            headers=headers,
            auth=HTTPDigestAuth("admin", "Sit12345"),
        )

        # Print the response
        print("Status Code:", response.status_code)
        # print("Response Body:\n", response.text)

        root = ET.fromstring(response.text)
        ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
        numOfMatches = root.find(".//isapi:numOfMatches", namespaces=ns)

        print(f"Searching in Face Database ID: {FDID}")

        if numOfMatches is not None and int(numOfMatches.text) >= 1:
            print("Matches found:\n", numOfMatches.text)
            matchesFound = numOfMatches.text

            personID = root.find(".//isapi:PID", namespaces=ns)
            # print(f"PID: {personID.text}")

            # name = root.find(".//isapi:name", namespaces=ns)
            # print(f"Name: {name.text}")

        else:
            print("No matches found.")
            return None
    else:
        print("ModeData is None.")
        return None

    return matchesFound, personID.text


def insert_into_face_db(frame, FDID, name):

    randomUUID = uuid.uuid4()

    success, encoded_image = cv.imencode(".jpg", frame)
    if not success:
        print("❌ Failed to encode frame")
        return None

    image_data = encoded_image.tobytes()

    # Build the XML payload
    xml_payload = f"""\
    <?xml version='1.0' encoding='UTF-8'?>
    <PictureUploadData>
        <FDID>{FDID}</FDID>
        <FaceAppendData>
            <name>{name}</name>
            <bornTime>2000-01-01</bornTime>
            <enable>true</enable>
            <customHumanID>{randomUUID}</customHumanID>
        </FaceAppendData>
    </PictureUploadData>
    """
    # <picURL>{image_filepath}</picURL>
    image_file = BytesIO(image_data)

    files = {
        "FaceAppendData": ("FaceAppendData.xml", xml_payload, "application/xml"),
        "importImage": ("image.jpg", image_file, "application/octet-stream"),
    }
    try:
        # Send the POST request
        response = requests.post(
            f"http://{NVR_IP}/ISAPI/Intelligent/FDLib/pictureUpload?type=concurrent",
            files=files,
            auth=HTTPDigestAuth("admin", "Sit12345"),
        )
        root = ET.fromstring(response.text)
        pid = root.text

        print("[FACE] 🔴 Inserted face into library")
        return pid

    except Exception:
        print("[ERROR] Error inserting cropped face snapshot into NVR.")
        return None


def safe_crop(img, x1, y1, x2, y2, padding=0):
    h, w, _ = img.shape
    x1 = max(x1 - padding, 0)
    y1 = max(y1 - padding, 0)
    x2 = min(x2 + padding, w)
    y2 = min(y2 + padding, h)
    return img[y1:y2, x1:x2]


# Estimates the facial area based on the nose, eyes and ears
def extract_face_from_nose(pose_points, frame):
    h, w = frame.shape[:2]

    nose = np.array(pose_points["nose"])
    l_eye = np.array(pose_points["left_eye"])
    r_eye = np.array(pose_points["right_eye"])
    l_ear = np.array(pose_points["left_ear"])
    r_ear = np.array(pose_points["right_ear"])

    # Get the vertical distance of nose to eyes
    average_y_of_eyes = (l_eye[1] + r_eye[1]) // 2
    nose_to_eye_height = abs(nose[1] - average_y_of_eyes) * 3
    eye_center_y = average_y_of_eyes

    # Add one unit (of nose_to_eye_height) above eye center, one below nose
    y1 = max(int(eye_center_y - nose_to_eye_height), 0)
    y2 = min(int(nose[1] + nose_to_eye_height) + 20, h)

    # Horizontal distance of bbox based on ears
    x1 = int(min(l_ear[0], r_eye[0] - 40))
    x2 = int(max(r_ear[0], l_eye[0] + 40))

    # check that bbox is valid
    if x2 <= x1 or y2 <= y1:
        print(x1, y1, x2, y2)
        raise ValueError("Invalid bounding box dimensions.")

    return (x1, y1, x2, y2)


def get_dist_nose_to_box(pose_points, detected_food_drinks, track_id):

    # compute edge of food/drink bbox edges to nose point
    # get nose point
    nose = np.array(pose_points["nose"])

    # get food/ drinks bounding box coords
    food_drinks_bbox = detected_food_drinks[track_id][0]  # [x1, y1, x2, y2]
    x1, y1, x2, y2 = food_drinks_bbox

    # Clamp the nose to the bounding box (to get closest point on box edge)
    clamped_x = np.clip(nose[0], x1, x2)
    clamped_y = np.clip(nose[1], y1, y2)

    # Compute distance from nose to closest point on the bbox (euclidean distance formula)
    return np.linalg.norm(nose - np.array([clamped_x, clamped_y]))


# Associate detected food/ drinks to person
def detection():
    # global running
    # global save_queue, process_queue
    # global detected_food_drinks_lock, pose_points_lock, flagged_foodbev_lock
    # global flagged_foodbev, pose_points, detected_food_drinks
    # global wrist_proximity_history

    db = sqlite3.connect("users.sqlite")

    while running:
        try:
            frame = process_queue.get(timeout=1)

        except queue.Empty:
            continue

        if frame is None or frame.size == 0:
            continue

        # shallow copy for reading in this thread
        with detected_incompliance_lock, pose_points_lock:
            local_pose_points = list(pose_points)
            local_detected_food_drinks = dict(detected_incompliance)

        for p in local_pose_points:
            for track_id in local_detected_food_drinks:

                with flagged_foodbev_lock:
                    if track_id in flagged_foodbev:
                        continue

                food_drinks_bbox = local_detected_food_drinks[track_id][0]
                x1, y1, x2, y2 = food_drinks_bbox

                try:
                    face_bbox = extract_face_from_nose(p, frame)
                    fx1, fy1, fx2, fy2 = map(int, face_bbox)

                except ValueError:
                    print("can't extract the face")
                    continue

                # if the top of food/ drink bbox is a percentage above the nose, ignore
                if y1 < p["nose"][1] * 0.95:
                    print("Food/ drink is above the nose, ignoring.")
                    continue

                # if area of food/ drink is more than 3.65 times the area of head, head is likely to be further away so ignore
                # if area of food/ drink is less than 10% of the area of head, food/ drink is likely to be further away so ignore
                area_food_drinks = abs(x1 - x2) * abs(y1 - y2)
                area_head = abs(fx1 - fx2) * abs(fy1 - fy2)
                if (
                    area_food_drinks >= area_head * 3.65
                    or area_food_drinks < area_head * 0.1
                ):
                    print("Food/ drink not at the same depth as person, ignoring.")
                    continue

                dist_nose_to_box = get_dist_nose_to_box(
                    p, local_detected_food_drinks, track_id
                )
                dist = min(
                    np.linalg.norm(
                        p["left_wrist"] - local_detected_food_drinks[track_id][1]
                    ),
                    np.linalg.norm(
                        p["right_wrist"] - local_detected_food_drinks[track_id][1]
                    ),
                )
                if dist <= WRIST_THRESHOLD and dist_nose_to_box <= NOSE_THRESHOLD:

                    now = time.time()

                    # Track wrist proximity times
                    if track_id not in wrist_proximity_history:
                        wrist_proximity_history[track_id] = []

                    wrist_proximity_history[track_id].append(now)

                    # Logging detection frame per track_Id
                    for track_id, timestamps in wrist_proximity_history.items():
                        print(
                            f"Track ID {track_id} has {len(timestamps)} proximity detections"
                        )

                    # Keep only timestamps within the last 2 seconds
                    recent_times = [
                        t
                        for t in wrist_proximity_history[track_id]
                        if now - t <= REQUIRED_DURATION
                    ]
                    wrist_proximity_history[track_id] = (
                        recent_times  # Prune old entries
                    )

                    if len(recent_times) >= REQUIRED_COUNT:
                        face_crop = None
                        face_crop = safe_crop(frame, fx1, fy1, fx2, fy2, padding=30)

                        if face_crop is not None and face_crop.size > 0:
                            try:
                                modeData = get_mode_data(frame)
                                matchesFound = get_face_comparison(
                                    modeData, INCOMPLIANCES_FDID
                                )

                                # match found
                                if matchesFound is not None:

                                    current_date = datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )

                                    query = """ SELECT p.PersonId, p.last_incompliance FROM Snapshot AS s JOIN Person p ON s.person_id = p.PersonId WHERE s.snapshotId = ?;"""
                                    cursor = db.execute(query, (matchesFound[1],))
                                    result = cursor.fetchone()

                                    if result:
                                        person_id, last_incompliance = result
                                        last_date = (
                                            last_incompliance[:10]
                                            if last_incompliance
                                            else None
                                        )
                                        today = current_date[:10]

                                        if last_date != today and last_date is not None:

                                            face_crop = cv.resize(
                                                face_crop,
                                                (
                                                    face_crop.shape[1] * 5,
                                                    face_crop.shape[0] * 5,
                                                ),
                                                cv.INTER_LINEAR,
                                            )
                                            snapshotId = insert_into_face_db(
                                                face_crop, INCOMPLIANCES_FDID, person_id
                                            )

                                            if snapshotId:
                                                update_query = """ UPDATE Person SET last_incompliance = ?, incompliance_count = incompliance_count + 1 WHERE PersonId = ?; """
                                                db.execute(
                                                    update_query,
                                                    (current_date, person_id),
                                                )
                                                db.commit()

                                                snapshot_query = """ INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected, imageURL, person_id, camera_id) VALUES (?, ?, ?, ?, ?, ?, ?)"""
                                                db.execute(
                                                    snapshot_query,
                                                    (
                                                        snapshotId,  # snapshotId = PID from NVR (1 PID for every unique image)
                                                        local_detected_food_drinks[
                                                            track_id
                                                        ][
                                                            2
                                                        ],  # confidence value
                                                        current_date,
                                                        str(
                                                            local_detected_food_drinks[
                                                                track_id
                                                            ][3]
                                                        ),  # detected object class id
                                                        f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
                                                        person_id,
                                                        1,  # temp camera id
                                                    ),
                                                )
                                                db.commit()

                                                # get the existing uuid of face and save incompliance img into folder
                                                # save_img(face_crop, str(person_id), today, "faces")
                                                save_img(
                                                    frame,
                                                    str(person_id),
                                                    today,
                                                    "incompliances",
                                                )

                                                print(
                                                    f"[ACTION] Similar face found 🟢: {person_id}. Saving incompliance snapshot and updated last incompliance date ✅"
                                                )

                                        # incompliance on the same date
                                        else:
                                            print(
                                                f"[ACTION] 🟣🟣🟣🟣 Similar face found but incompliance on same date, ignoring."
                                            )

                                        with flagged_foodbev_lock:
                                            flagged_foodbev.append(
                                                track_id
                                            )  # save track id of bottle
                                # no match
                                else:
                                    with flagged_foodbev_lock:
                                        flagged_foodbev.append(
                                            track_id
                                        )  # save track id of bottle

                                    current_date = datetime.now().strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    )
                                    today = current_date[:10]

                                    cursor = db.execute(
                                        """ INSERT INTO Person (last_incompliance, incompliance_count) VALUES (?, 1) RETURNING PersonId;""",
                                        (current_date,),
                                    )
                                    person_id = cursor.fetchone()[0]

                                    face_crop = cv.resize(
                                        face_crop,
                                        (
                                            face_crop.shape[1] * 5,
                                            face_crop.shape[0] * 5,
                                        ),
                                        cv.INTER_LINEAR,
                                    )
                                    snapshotId = insert_into_face_db(
                                        face_crop, INCOMPLIANCES_FDID, person_id
                                    )

                                    os.makedirs(
                                        os.path.join(
                                            "web",
                                            "static",
                                            "incompliances",
                                            str(person_id),
                                        ),
                                        exist_ok=True,
                                    )
                                    # save cropped face area save it for matching next time

                                    if snapshotId:
                                        snapshot_query = """ INSERT INTO Snapshot (snapshotId, confidence, time_generated, object_detected, imageURL, person_id, camera_id) VALUES (?, ?, ?, ?, ?, ?, ?);"""
                                        db.execute(
                                            snapshot_query,
                                            (
                                                snapshotId,
                                                local_detected_food_drinks[track_id][
                                                    2
                                                ],  # confidence value
                                                current_date,
                                                str(
                                                    local_detected_food_drinks[
                                                        track_id
                                                    ][3]
                                                ),  # detected object class id
                                                f"incompliances/{person_id}/Person_{person_id}_{today}.jpg",
                                                person_id,
                                                1,  # temp camera id
                                            ),
                                        )
                                        db.commit()

                                        # save_img(face_crop, str(person_id), today, "faces")
                                        save_img(
                                            frame,
                                            str(person_id),
                                            today,
                                            "incompliances",
                                        )

                                        print(
                                            f"[NEW] No face found 🟡. Saving incompliance snapshot and updated last incompliance date ✅"
                                        )
                                        time.sleep(
                                            3
                                        )  # give time for the face to be modeled in NVR, prevents double inserts of same incompliances

                            except Exception as e:
                                print(e)
                                continue
                else:
                    print("Pose not near drink, skipping.")

    db.close()
