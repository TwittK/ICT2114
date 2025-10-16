import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import uuid
import cv2 as cv
from io import BytesIO
import os
from datetime import datetime, timedelta


class NVR:
    """
    A class to interact with a Network Video Recorder (NVR) for face detection and management
    via ISAPI endpoints, for face comparison, and face database insertion.
    """

    def __init__(self, nvr_ip, fdid, username, password):
        """
        Initializes the NVR instance with connection credentials.

        Parameters:
          nvr_ip (str): IP address of the NVR.
          fdid (str): Face database ID for face-related queries.
          username (str): Username for NVR authentication.
          password (str): Password for NVR authentication.
        """
        self.fdid = fdid
        self.username = username
        self.password = password
        self.nvr_ip = nvr_ip

    def get_mode_data(self, face):
        url = f"http://{self.nvr_ip}/ISAPI/Intelligent/analysisImage/face"

        # Send request
        success, encoded_image = cv.imencode(".jpg", face)
        if not success:
            return None

        # Get modeData of face for face comparison
        image_data = encoded_image.tobytes()
        headers = {"Content-Type": "application/octet-stream"}
        response = requests.post(
            url,
            data=image_data,
            headers=headers,
            auth=HTTPDigestAuth(self.username, self.password),
        )

        # Find modeData in message body
        if response.ok:
            try:
                ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
                root = ET.fromstring(response.text)
                mode_data_elem = root.find(".//isapi:modeData", namespaces=ns)

                if mode_data_elem is not None:
                    mode_data = mode_data_elem.text
                else:
                    return None

            except ET.ParseError:
                return None
        else:
            return None

        return mode_data

    def get_face_comparison(self, mode_data):
        """
        Uses modeData to search for matching faces in the NVR's face database.

        Parameters:
          mode_data (str): Mode data string obtained from get_mode_data.

        Returns:
          tuple: (matches_found, person_id)
            matches_found (int or str): Number of matches found (0 if none).
            person_id (str or None): The matched person's ID if found, otherwise None.

          Returns (None, None) if mode_data is None.
        """
        if mode_data is not None:

            iv = os.urandom(16).hex()
            url = f"http://{self.nvr_ip}/ISAPI/Intelligent/FDLib/FDSearch?security=1&iv={iv}"

            # Build the XML payload
            random_uuid = uuid.uuid4()
            xml_payload = f"""<?xml version="1.0" encoding="utf-8"?>
      <FDSearchDescription>
          <FDID>{self.fdid}</FDID>
          <OccurrencesInfo>
              <enabled>true</enabled>
              <occurrences>0</occurrences>
              <occurrencesSearchType>greaterThanOrEqual</occurrencesSearchType>
          </OccurrencesInfo>
          <FaceModeList>
              <FaceMode>
                  <ModeInfo>
                      <similarity>80</similarity>
                      <modeData>{mode_data}</modeData>
                  </ModeInfo>
              </FaceMode>
          </FaceModeList>
          <searchID>{random_uuid}</searchID>
          <maxResults>1</maxResults>
          <searchResultPosition>0</searchResultPosition>
      </FDSearchDescription>
      """

            headers = {"Content-Type": "application/xml"}

            # Send request
            response = requests.post(
                url,
                data=xml_payload.encode("utf-8"),
                headers=headers,
                auth=HTTPDigestAuth(self.username, self.password),
            )

            root = ET.fromstring(response.text)
            ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
            num_of_matches = root.find(".//isapi:numOfMatches", namespaces=ns)

            # Check if there's any match
            if num_of_matches is not None and int(num_of_matches.text) >= 1:
                matches_found = num_of_matches.text
                person_id = root.find(".//isapi:PID", namespaces=ns)

            else:
                return (0, None)

        else:
            return (None, None)

        return matches_found, person_id.text

    def insert_into_face_db(self, face, name):
        """
        Inserts a new face entry into the NVR's face database along with metadata.

        Parameters:
          face (np.ndarray): Image of the face to insert.
          name (str): Name of the person associated with the face.

        Returns:
          str or None: The new face's ID (PID) if insertion is successful, None otherwise.
        """
        random_uuid = uuid.uuid4()

        # Prepare face image payload
        success, encoded_image = cv.imencode(".jpg", face)
        if not success:
            return None

        image_data = encoded_image.tobytes()
        image_file = BytesIO(image_data)

        # Build the XML payload
        xml_payload = f"""\
    <?xml version='1.0' encoding='UTF-8'?>
    <PictureUploadData>
        <FDID>{self.fdid}</FDID>
        <FaceAppendData>
            <name>{name}</name>
            <bornTime>2000-01-01</bornTime>
            <enable>true</enable>
            <customHumanID>{random_uuid}</customHumanID>
        </FaceAppendData>
    </PictureUploadData>
    """

        files = {
            "FaceAppendData": ("FaceAppendData.xml", xml_payload, "application/xml"),
            "importImage": ("image.jpg", image_file, "application/octet-stream"),
        }

        try:
            # Send the POST request
            response = requests.post(
                f"http://{self.nvr_ip}/ISAPI/Intelligent/FDLib/pictureUpload?type=concurrent",
                files=files,
                auth=HTTPDigestAuth(self.username, self.password),
            )
            root = ET.fromstring(response.text)
            pid = root.text
            return pid

        except Exception:
            return None

    def download_clip_by_time(self, start_time, end_time, track_id):
        """
        A generator that downloads a video clip using the NVR's HTTP ISAPI and yields JPEG frames.
        Uses the search-first approach which is more reliable for NVRs.
        """
        # Step 1: Search for recordings in the time range
        search_url = f"http://{self.nvr_ip}/ISAPI/ContentMgmt/search"

        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build search XML
        search_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<CMSearchDescription>"
            "<searchID>C" + str(uuid.uuid4()).replace("-", "") + "</searchID>"
            f"<trackList><trackID>{track_id}</trackID></trackList>"
            "<timeSpanList>"
            "<timeSpan>"
            f"<startTime>{start_str}</startTime>"
            f"<endTime>{end_str}</endTime>"
            "</timeSpan>"
            "</timeSpanList>"
            "<maxResults>40</maxResults>"
            "<searchResultPosition>0</searchResultPosition>"
            "<metadataList>"
            "<metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor>"
            "</metadataList>"
            "</CMSearchDescription>"
        )

        print(f"🔍 Searching for recordings on track {track_id}")
        print(f"Time range: {start_str} to {end_str}")

        try:
            headers = {"Content-Type": "application/xml"}
            search_response = requests.post(
                search_url,
                data=search_xml.encode("utf-8"),
                headers=headers,
                auth=HTTPDigestAuth(self.username, self.password),
                timeout=10,
            )

            if search_response.status_code != 200:
                print(f"❌ Search failed with status {search_response.status_code}")
                print(f"Response: {search_response.text}")
                return

            # Parse search results to get playbackURI
            root = ET.fromstring(search_response.text)
            ns = {"ns": "http://www.isapi.org/ver20/XMLSchema"}

            playback_uri = root.find(".//ns:playbackURI", ns)
            if playback_uri is None or not playback_uri.text:
                print("❌ No recordings found in the specified time range")
                print(f"Search response: {search_response.text[:500]}")
                return

            playback_uri_text = playback_uri.text
            print(f"✅ Found recording: {playback_uri_text}")

            # Step 2: Download using the playbackURI from search results
            download_url = f"http://{self.nvr_ip}/ISAPI/ContentMgmt/download"

            download_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<downloadRequest version="1.0" xmlns="http://www.isapi.org/ver20/XMLSchema">'
                f"<playbackURI>{playback_uri_text}</playbackURI>"
                "</downloadRequest>"
            )

            print(f"📥 Downloading video...")

            response = requests.post(
                download_url,
                data=download_xml.encode("utf-8"),
                headers=headers,
                auth=HTTPDigestAuth(self.username, self.password),
                stream=True,
                timeout=30,
            )

            if response.status_code != 200:
                print(f"❌ Download failed with status {response.status_code}")
                print(f"Response: {response.text}")
                return

            # Read video data
            video_data = response.content

            if len(video_data) == 0:
                print("❌ No video data received")
                return

            print(f"✅ Received {len(video_data)} bytes of video data")

            # Save and process with OpenCV
            temp_video_path = f"/tmp/clip_{uuid.uuid4()}.mp4"
            with open(temp_video_path, "wb") as f:
                f.write(video_data)

            cap = cv.VideoCapture(temp_video_path)
            if not cap.isOpened():
                print("❌ Could not open video file")
                os.remove(temp_video_path)
                return

            frame_count = 0
            while True:
                success, frame = cap.read()
                if not success:
                    break

                ret, buffer = cv.imencode(".jpg", frame)
                if not ret:
                    continue

                frame_count += 1
                yield buffer.tobytes()

            cap.release()
            os.remove(temp_video_path)
            print(f"✅ Streamed {frame_count} frames successfully")

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
        except Exception as e:
            print(f"❌ Error: {e}")
