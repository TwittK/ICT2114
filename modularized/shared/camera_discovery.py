import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import sqlite3
from database import create_camera
from datetime import datetime

class CameraDiscovery:
    def __init__(self, username="admin", password="Sit12345"):
        self.username = username
        self.password = password
        # Support both namespace variations
        self.ns = {
            "hik": "http://www.hikvision.com/ver20/XMLSchema",
            "isapi": "http://www.isapi.org/ver20/XMLSchema"
        }

    def discover_camera(self, camera_ip):
        """Discover camera capabilities and return configuration"""
        try:
            device_info = self._get_device_info(camera_ip)
            network_info = self._get_network_info(camera_ip)
            stream_info = self._get_stream_info(camera_ip)
            time_info = self._get_time_info(camera_ip)
            ntp_info = self._get_ntp_info(camera_ip)
            
            if device_info and network_info and stream_info and time_info:
                return {
                    'ip_address': camera_ip,
                    'device_name': device_info.get('device_name', f'Camera_{camera_ip}'),
                    'model': device_info.get('model', 'Unknown'),
                    'resolution': stream_info.get('resolution', 1080),
                    'frame_rate': stream_info.get('frame_rate', 25),
                    'encoding': stream_info.get('encoding', 'H.265'),
                    'subnet_mask': network_info.get('subnet_mask', '255.255.255.0'),
                    'gateway': network_info.get('gateway', '192.168.1.1'),
                    'camera_ip_type': network_info.get('ip_type', 'static'),
                    'timezone': time_info.get('timezone', 'Asia/Singapore'),
                    'sync_with_ntp': time_info.get('sync_with_ntp', 0),
                    'ntp_server_address': ntp_info.get('ntp_server', 'pool.ntp.org'),
                    'time': time_info.get('local_time', datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
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
                
                # Try multiple XPath approaches for IP type
                ip_type_elem = None
                ip_type_elem = (root.find(".//hik:IPAddress/hik:addressingType", namespaces=self.ns) or 
                              root.find(".//isapi:IPAddress/isapi:addressingType", namespaces=self.ns))
                
                if ip_type_elem is None:
                    ip_type_elem = root.find(".//addressingType")
                
                if ip_type_elem is None:
                    for elem in root.iter():
                        if elem.tag.endswith('addressingType'):
                            ip_type_elem = elem
                            break
                
                # Get other network elements
                ip_elem = (root.find(".//hik:IPAddress/hik:ipAddress", namespaces=self.ns) or 
                          root.find(".//isapi:IPAddress/isapi:ipAddress", namespaces=self.ns) or
                          root.find(".//ipAddress"))
                
                mask_elem = (root.find(".//hik:IPAddress/hik:subnetMask", namespaces=self.ns) or 
                           root.find(".//isapi:IPAddress/isapi:subnetMask", namespaces=self.ns) or
                           root.find(".//subnetMask"))
                
                gateway_elem = (root.find(".//hik:IPAddress/hik:DefaultGateway/hik:ipAddress", namespaces=self.ns) or 
                              root.find(".//isapi:IPAddress/isapi:DefaultGateway/isapi:ipAddress", namespaces=self.ns) or
                              root.find(".//DefaultGateway/ipAddress"))
                
                ip_type = 'dhcp'  # default
                if ip_type_elem is not None and ip_type_elem.text:
                    ip_type = ip_type_elem.text.strip()
                
                return {
                    'ip_address': ip_elem.text if ip_elem is not None else camera_ip,
                    'subnet_mask': mask_elem.text if mask_elem is not None else '255.255.255.0',
                    'gateway': gateway_elem.text if gateway_elem is not None else '192.168.1.1',
                    'ip_type': ip_type
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
                
                # Try multiple XPath approaches for each element
                width_elem = None
                height_elem = None
                codec_elem = None
                framerate_elem = None
                
                # Approach 1: Try both namespaces with full path
                width_elem = (root.find(".//hik:videoResolutionWidth", namespaces=self.ns) or 
                             root.find(".//isapi:videoResolutionWidth", namespaces=self.ns))
                height_elem = (root.find(".//hik:videoResolutionHeight", namespaces=self.ns) or 
                              root.find(".//isapi:videoResolutionHeight", namespaces=self.ns))
                codec_elem = (root.find(".//hik:videoCodecType", namespaces=self.ns) or 
                             root.find(".//isapi:videoCodecType", namespaces=self.ns))
                framerate_elem = (root.find(".//hik:maxFrameRate", namespaces=self.ns) or 
                                 root.find(".//isapi:maxFrameRate", namespaces=self.ns))
                
                # Approach 2: Try without namespace
                if width_elem is None:
                    width_elem = root.find(".//videoResolutionWidth")
                if height_elem is None:
                    height_elem = root.find(".//videoResolutionHeight")
                if codec_elem is None:
                    codec_elem = root.find(".//videoCodecType")
                if framerate_elem is None:
                    framerate_elem = root.find(".//maxFrameRate")
                
                # Approach 3: Try direct search in all elements
                if width_elem is None:
                    for elem in root.iter():
                        if elem.tag.endswith('videoResolutionWidth'):
                            width_elem = elem
                            break
                
                if height_elem is None:
                    for elem in root.iter():
                        if elem.tag.endswith('videoResolutionHeight'):
                            height_elem = elem
                            break
                
                if codec_elem is None:
                    for elem in root.iter():
                        if elem.tag.endswith('videoCodecType'):
                            codec_elem = elem
                            break
                
                if framerate_elem is None:
                    for elem in root.iter():
                        if elem.tag.endswith('maxFrameRate'):
                            framerate_elem = elem
                            break
                
                width = int(width_elem.text) if width_elem is not None else 1920
                height = int(height_elem.text) if height_elem is not None else 1080
                
                # Convert resolution to standard format
                if width >= 2560:  # 4K or higher
                    resolution = 2160
                elif width >= 1920 and height >= 1080:
                    resolution = 1080
                elif width >= 1280 and height >= 720:
                    resolution = 720
                else:
                    resolution = 480
                
                # Debug frame rate conversion
                frame_rate = 25  # default
                if framerate_elem is not None and framerate_elem.text:
                    try:
                        raw_framerate = int(framerate_elem.text)
                        
                        # Convert from format like 2500 to 25 FPS
                        if raw_framerate >= 100:
                            frame_rate = raw_framerate // 100
                        else:
                            frame_rate = raw_framerate
                            
                    except ValueError as e:
                        frame_rate = 25
                else:
                    print(f"Debug - No frame rate element found for {camera_ip}, using default: {frame_rate}")
                
                result = {
                    'resolution': resolution,
                    'frame_rate': frame_rate,
                    'encoding': codec_elem.text if codec_elem is not None else 'H.265'
                }
                
                return result
                
            except (ET.ParseError, ValueError) as e:
                print(f"Debug - Stream XML Parse Error for {camera_ip}: {e}")
                return None
        else:
            print(f"Debug - Stream request failed for {camera_ip}, status: {response.status_code}")
        return None

    def _get_time_info(self, camera_ip):
        """Get time configuration"""
        url = f"http://{camera_ip}/ISAPI/System/time"
        response = requests.get(url, auth=HTTPDigestAuth(self.username, self.password), timeout=10)
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                
                # Try both namespace variations
                time_mode_elem = (root.find(".//hik:timeMode", namespaces=self.ns) or 
                                root.find(".//isapi:timeMode", namespaces=self.ns))
                local_time_elem = (root.find(".//hik:localTime", namespaces=self.ns) or 
                                 root.find(".//isapi:localTime", namespaces=self.ns))
                timezone_elem = (root.find(".//hik:timeZone", namespaces=self.ns) or 
                               root.find(".//isapi:timeZone", namespaces=self.ns))
                
                # Determine if NTP is enabled (manual = 0, NTP = 1)
                sync_with_ntp = 0
                if time_mode_elem is not None and time_mode_elem.text:
                    sync_with_ntp = 1 if time_mode_elem.text.lower() == 'ntp' else 0
                
                # Parse timezone (CST-8:00:00 -> Asia/Singapore)
                timezone = 'Asia/Singapore'  # default
                if timezone_elem is not None and timezone_elem.text:
                    tz_text = timezone_elem.text
                    if 'CST-8' in tz_text or '+08:00' in tz_text:
                        timezone = 'Asia/Singapore'
                    elif 'UTC' in tz_text or '+00:00' in tz_text:
                        timezone = 'UTC'
                
                # Parse local time format (2025-07-16T17:07:30+08:00)
                local_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                if local_time_elem is not None and local_time_elem.text:
                    try:
                        # Remove timezone offset for database storage
                        time_str = local_time_elem.text.split('+')[0].split('-')[0:3]
                        if len(time_str) == 3:
                            local_time = local_time_elem.text.split('+')[0]
                        else:
                            local_time = local_time_elem.text[:19]  # Take first 19 chars (YYYY-MM-DDTHH:MM:SS)
                    except:
                        local_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                
                return {
                    'timezone': timezone,
                    'sync_with_ntp': sync_with_ntp,
                    'local_time': local_time
                }
            except ET.ParseError:
                return None
        return None

    def _get_ntp_info(self, camera_ip):
        url = f"http://{camera_ip}/ISAPI/System/time/ntpServers"
        response = requests.get(url, auth=HTTPDigestAuth(self.username, self.password), timeout=10)
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.text)
                
                # Try multiple XPath approaches for NTP server hostname
                hostname_elem = None
                
                # Approach 1: Try both namespaces with full path
                hostname_elem = (root.find(".//hik:NTPServer/hik:hostName", namespaces=self.ns) or 
                               root.find(".//isapi:NTPServer/isapi:hostName", namespaces=self.ns))
                
                # Approach 2: Try without namespace
                if hostname_elem is None:
                    hostname_elem = root.find(".//hostName")
                
                # Approach 3: Try direct search in all elements
                if hostname_elem is None:
                    for elem in root.iter():
                        if elem.tag.endswith('hostName'):
                            hostname_elem = elem
                            break
                
                ntp_server = 'pool.ntp.org'  # default
                if hostname_elem is not None and hostname_elem.text:
                    ntp_server = hostname_elem.text.strip()
                
                result = {
                    'ntp_server': ntp_server
                }
                
                return result
                
            except ET.ParseError as e:
                return None
        else:
            print(f"Debug - NTP request failed for {camera_ip}, status: {response.status_code}")
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
                    gateway=config['gateway'],
                    timezone=config['timezone'],
                    sync_with_ntp=config['sync_with_ntp'],
                    ntp_server_address=config['ntp_server_address'],
                    time=config['time']
                )
                
                if success:
                    print(f"✅ Added camera: {config['device_name']} ({camera_ip})")
                else:
                    print(f"❌ Failed to add camera: {camera_ip}")
            else:
                print(f"❌ Could not discover camera at {camera_ip}")
        
        conn.close()