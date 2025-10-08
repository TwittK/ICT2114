import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import uuid
import cv2 as cv
from io import BytesIO
import os

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
    response = requests.post(url, data=image_data, headers=headers, auth=HTTPDigestAuth(self.username, self.password))

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
