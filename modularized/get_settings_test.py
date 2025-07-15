import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

def fetch_current_stream_settings(camera_ip, username="admin", password="Sit12345", channel="101"):
    url = f"http://{camera_ip}/ISAPI/Streaming/channels/{channel}"
    response = requests.get(url, auth=HTTPDigestAuth(username, password))

    if response.status_code == 200:
        return response.text  # full current XML config
    else:
        print(f"❌ Failed to fetch current settings. Status: {response.status_code}")
        return None

def get_camera_info(camera_ip, username="admin", password="Sit12345", channel ='101'):
    # url = f"http://{camera_ip}/ISAPI/System/deviceInfo"
    # url = f"http://{camera_ip}/ISAPI/System/Network/interfaces"
    url = f"http://{camera_ip}/ISAPI/Streaming/channels/{channel}"

    response = requests.get(url, auth=HTTPDigestAuth(username, password))
    print("Status Code:", response.status_code)

    if response.ok:
        try:
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            root = ET.fromstring(response.text)
            print(response.text)

            res_elem = root.find(".//hik:videoResolutionWidth", namespaces=ns)
            codec_elem = root.find(".//hik:videoCodecType", namespaces=ns)

            print(f"📺 Resolution: {res_elem.text if res_elem is not None else 'N/A'}")
            print(f"🎞️ Codec: {codec_elem.text if codec_elem is not None else 'N/A'}")

            # Find the first IPv4 address
            # ip_elem = root.find(".//hik:ipAddress", namespaces=ns)
            # mask_elem = root.find(".//hik:subnetMask", namespaces=ns)
            # gateway_elem = root.find(".//hik:DefaultGateway/hik:ipAddress", namespaces=ns)

            # print(f"🌐 IP Address: {ip_elem.text if ip_elem is not None else 'N/A'}")
            # print(f"🛡️ Subnet Mask: {mask_elem.text if mask_elem is not None else 'N/A'}")
            # print(f"🚪 Gateway: {gateway_elem.text if gateway_elem is not None else 'N/A'}")
        except ET.ParseError as e:
            print("❌ XML parsing error:", e)
    else:
        print("❌ Request failed:", response.status_code, response.reason)


def update_camera_stream_settings(camera_ip, width=1280, height=720, username="admin", password="Sit12345", channel="101"):
    from xml.etree import ElementTree as ET

    current_config = fetch_current_stream_settings(camera_ip, username, password, channel)
    if not current_config:
        return

    root = ET.fromstring(current_config)
    ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}

    # Update resolution
    ET.register_namespace('', ns["hik"])  # ensures no "ns0" prefix in XML output
    res_width = root.find(".//hik:videoResolutionWidth", namespaces=ns)
    res_height = root.find(".//hik:videoResolutionHeight", namespaces=ns)

    if res_width is not None:
        res_width.text = str(width)
    if res_height is not None:
        res_height.text = str(height)

    updated_xml = ET.tostring(root, encoding="utf-8")

    url = f"http://{camera_ip}/ISAPI/Streaming/channels/{channel}"
    headers = {"Content-Type": "application/xml"}

    response = requests.put(
        url,
        data=updated_xml,
        headers=headers,
        auth=HTTPDigestAuth(username, password)
    )

    if response.status_code == 200:
        print("✅ Stream settings updated successfully.")
    else:
        print(f"❌ Failed to update. Status: {response.status_code} - {response.reason}")
        print("Response:", response.text)        

update_camera_stream_settings("192.168.1.64")