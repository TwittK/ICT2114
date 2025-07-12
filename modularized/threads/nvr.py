import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import uuid
import time
import cv2 as cv
from io import BytesIO
import os

class NVR:
  def __init__(self, nvr_ip, fdid, username, password):
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
          modeData = mode_data_elem.text
        else:
          return None

      except ET.ParseError as e:
        return None
    else:
      return None

    return modeData
  
  def get_face_comparison(self, modeData):
    if modeData is not None:

      iv = os.urandom(16).hex()
      url = f"http://{self.nvr_ip}/ISAPI/Intelligent/FDLib/FDSearch?security=1&iv={iv}"

      # Build the XML payload
      randomUUID = uuid.uuid4()
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
                      <modeData>{modeData}</modeData>
                  </ModeInfo>
              </FaceMode>
          </FaceModeList>
          <searchID>{randomUUID}</searchID>
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
      numOfMatches = root.find(".//isapi:numOfMatches", namespaces=ns)

      # Check if there's any match
      if numOfMatches is not None and int(numOfMatches.text) >= 1:
        matchesFound = numOfMatches.text
        personID = root.find(".//isapi:PID", namespaces=ns)

      else:
        return 0
      
    else:
      return None

    return matchesFound, personID.text
  
  def insert_into_face_db(self, face, name):

    randomUUID = uuid.uuid4()

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
            <customHumanID>{randomUUID}</customHumanID>
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
