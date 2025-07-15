import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import sqlite3
from database import create_camera

class CameraDiscovery:
    def __init__(self, username="admin", password="Sit12345"):
        self.username = username
        self.password = password
        self.ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}

    def discover_camera(self, camera_ip):
        """Discover camera capabilities and return configuration"""
        try:
            device_info = self._get_device_info(camera_ip)
            network_info = self._get_network_info(camera_ip)
            stream_info = self._get_stream_info(camera_ip)
            
            if device_info and network_info and stream_info:
                return {
                    'ip_address': camera_ip,
                    'device_name': device_info.get('device_name', f'Camera_{camera_ip}'),
                    'model': device_info.get('model', 'Unknown'),
                    'resolution': stream_info.get('resolution', 1080),
                    'frame_rate': stream_info.get('frame_rate', 30),
                    'encoding': stream_info.get('encoding', 'H.265'),
                    'subnet_mask': network_info.get('subnet_mask', '255.255.255.0'),
                    'gateway': network_info.get('gateway', '192.168.1.1'),
                    'camera_ip_type': network_info.get('ip_type', 'static')
                }
        except Exception as e:
            print(f"❌ Failed to discover camera {camera_ip}: {e}")
            return None

    def _get_device_info(self, camera_ip):
        """Get basic device information"""
        url = f"http://{camera_ip}/ISAPI/System/deviceInfo"
        response = requests.get(url, auth=HTTPDigestAuth(self.username, self.password), timeout=10)
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                device_name = root.find(".//hik:deviceName", namespaces=self.ns)
                model = root.find(".//hik:model", namespaces=self.ns)
                
                return {
                    'device_name': device_name.text if device_name is not None else f'Camera_{camera_ip}',
                    'model': model.text if model is not None else 'Unknown'
                }
            except ET.ParseError:
                return None
        return None

    def _get_network_info(self, camera_ip):
        """Get network configuration"""
        url = f"http://{camera_ip}/ISAPI/System/Network/interfaces"
        response = requests.get(url, auth=HTTPDigestAuth(self.username, self.password), timeout=10)
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                ip_elem = root.find(".//hik:ipAddress", namespaces=self.ns)
                mask_elem = root.find(".//hik:subnetMask", namespaces=self.ns)
                gateway_elem = root.find(".//hik:DefaultGateway/hik:ipAddress", namespaces=self.ns)
                ip_type_elem = root.find(".//hik:addressingType", namespaces=self.ns)
                
                return {
                    'ip_address': ip_elem.text if ip_elem is not None else camera_ip,
                    'subnet_mask': mask_elem.text if mask_elem is not None else '255.255.255.0',
                    'gateway': gateway_elem.text if gateway_elem is not None else '192.168.1.1',
                    'ip_type': 'static' if ip_type_elem is not None and ip_type_elem.text == 'static' else 'dhcp'
                }
            except ET.ParseError:
                return None
        return None

    def _get_stream_info(self, camera_ip, channel="101"):
        """Get streaming configuration"""
        url = f"http://{camera_ip}/ISAPI/Streaming/channels/{channel}"
        response = requests.get(url, auth=HTTPDigestAuth(self.username, self.password), timeout=10)
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                width_elem = root.find(".//hik:videoResolutionWidth", namespaces=self.ns)
                height_elem = root.find(".//hik:videoResolutionHeight", namespaces=self.ns)
                codec_elem = root.find(".//hik:videoCodecType", namespaces=self.ns)
                framerate_elem = root.find(".//hik:videoFrameRate", namespaces=self.ns)
                
                width = int(width_elem.text) if width_elem is not None else 1920
                height = int(height_elem.text) if height_elem is not None else 1080
                
                # Convert resolution to standard format
                if width >= 1920 and height >= 1080:
                    resolution = 1080
                elif width >= 1280 and height >= 720:
                    resolution = 720
                else:
                    resolution = 480
                
                return {
                    'resolution': resolution,
                    'frame_rate': int(framerate_elem.text) if framerate_elem is not None else 30,
                    'encoding': codec_elem.text if codec_elem is not None else 'H.265'
                }
            except (ET.ParseError, ValueError):
                return None
        return None

    def scan_network_for_cameras(self, network_range="192.168.1."):
        """Scan network range for Hikvision cameras"""
        discovered_cameras = []
        
        for i in range(1, 255):
            camera_ip = f"{network_range}{i}"
            print(f"🔍 Scanning {camera_ip}...")
            
            config = self.discover_camera(camera_ip)
            if config:
                print(f"✅ Found camera: {config['device_name']} at {camera_ip}")
                discovered_cameras.append(config)
        
        return discovered_cameras

    def auto_populate_database(self, camera_ips, lab_name="E2-L6-016", user_id=1):
        """Auto-populate database with discovered cameras"""
        conn = sqlite3.connect('users.sqlite')
        cursor = conn.cursor()
        
        # Get lab ID
        cursor.execute("SELECT LabId FROM Lab WHERE lab_name = ?", (lab_name,))
        lab_result = cursor.fetchone()
        if not lab_result:
            print(f"❌ Lab '{lab_name}' not found")
            conn.close()
            return
        
        lab_id = lab_result[0]
        
        for camera_ip in camera_ips:
            print(f"🔍 Discovering camera at {camera_ip}...")
            config = self.discover_camera(camera_ip)
            
            if config:
                # Check if camera already exists
                cursor.execute("SELECT COUNT(*) FROM Camera WHERE ip_address = ?", (camera_ip,))
                if cursor.fetchone()[0] > 0:
                    print(f"⚠️ Camera {camera_ip} already exists in database")
                    continue
                
                # Create camera with discovered config
                success = create_camera(
                    name=config['device_name'],
                    camera_user_id=user_id,
                    camera_lab_id=lab_id,
                    resolution=config['resolution'],
                    frame_rate=config['frame_rate'],
                    encoding=config['encoding'],
                    camera_ip_type=config['camera_ip_type'],
                    ip_address=config['ip_address'],
                    subnet_mask=config['subnet_mask'],
                    gateway=config['gateway']
                )
                
                if success:
                    print(f"✅ Added camera: {config['device_name']} ({camera_ip})")
                else:
                    print(f"❌ Failed to add camera: {camera_ip}")
            else:
                print(f"❌ Could not discover camera at {camera_ip}")
        
        conn.close()