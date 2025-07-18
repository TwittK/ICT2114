from flask import Flask, request, session, redirect, url_for, render_template, flash, Response, jsonify
from functools import wraps
from data_source.camera_dao import CameraDAO
from datetime import datetime
import sqlite3
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

import cv2
from database import verify_user, update_last_login, get_all_users, get_all_roles, get_all_permissions, get_all_rolepermissions
from shared.camera_manager import CameraManager
from shared.camera_discovery import CameraDiscovery
import queue
from web.utils import check_permission

DATABASE = "users.sqlite"
SNAPSHOT_FOLDER = "snapshots"

app = Flask(__name__)

class_id_to_label = {
    39: "Bottle",
    40: "Wine Glass",
    41: "Cup",
}

def dict_factory(cursor, row):
    """Convert sqlite3.Row to dictionary"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def require_permission(permission_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                flash('You must be logged in to access this page.', 'danger')
                return redirect(url_for('index'))

            role_name = session.get('role')
            if not role_name:
                flash('No role assigned to user.', 'danger')
                return redirect(url_for('index'))

            conn = sqlite3.connect(DATABASE)
            has_permission = check_permission(conn, role_name, permission_name)
            conn.close()

            if not has_permission:
                flash(f"Permission '{permission_name}' required.", 'danger')
                return redirect(url_for('index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.context_processor
def inject_labs_with_cameras():
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute("""
                   SELECT l.LabId,
                          l.lab_name,
                          c.CameraId,
                          c.name
                   FROM Lab l
                            LEFT JOIN Camera c ON c.camera_lab_id = l.LabId
                   ORDER BY l.lab_name ASC, c.name ASC
                   """)

    rows = cursor.fetchall()
    conn.close()

    # Group cameras under their labs.
    labs = {}
    for lab_id, lab_name, camera_id, camera_name in rows:
        if lab_id not in labs:
            labs[lab_id] = {
                "lab_id": lab_id,
                "lab_name": lab_name,
                "cameras": []
            }
        # Might be None if no camera exists.
        if camera_id:
            labs[lab_id]["cameras"].append({
                "camera_id": camera_id,
                "camera_name": camera_name,
            })

    # Ensure all labs have a 'cameras' key, at least empty list.
    for lab in labs.values():
        if "cameras" not in lab or lab["cameras"] is None:
            lab["cameras"] = []

    return dict(labs=list(labs.values()))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = verify_user(email, password)

        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['role'] = user['role']

            update_last_login(user['id'])

            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password!', 'error')

    return render_template('login.html')


@app.route('/', methods=["GET", "POST"])
@login_required
def index():
    lab_name = request.args.get("lab")
    camera_name = request.args.get("camera")

    # ✅ Store selected camera in session
    if camera_name:
        session['selected_camera'] = {
            'name': camera_name,
            'lab': lab_name
        }
        print("✅ Selected camera stored in session:", session['selected_camera'])

    is_deleting_camera = request.args.get("delete", "0") == "1"
    is_adding_camera = request.args.get("add", "0") == "1"
    today_str = datetime.now().strftime('%Y-%m-%d')

    results = []

    # Open database connection from permission verification
    try:
        conn = sqlite3.connect(DATABASE)
    except Exception:
        return redirect(url_for("index"))
    role = session.get('role')
    if role is None:
        return redirect(url_for("index"))
    cam_management = check_permission(conn, role, "camera_management")
    user_management = check_permission(conn, role, "user_management")

    # Create camera inside the database - ADMIN ONLY
    if request.method == "POST" and is_adding_camera and lab_name and cam_management:
        try:
            if not request.is_json:
                flash("Invalid request.", "danger")
                return redirect(url_for("index"))
            
            data = request.get_json()
            device_info = data.get("device_info")

            # Device info not found
            if not device_info:
                flash("Error retrieving device info.", "danger")
                return redirect(url_for("index"))
            
            user_id = session.get("user_id")
            dao = CameraDAO("users.sqlite")

            # Insert camera into database
            camera_id, message = dao.add_new_camera(
                lab_name=lab_name,
                user_id=user_id,
                device_info=device_info
            )
            if camera_id is None:
                flash("Error inserting camera into database.", "danger")
                return redirect(url_for("index"))
            
            # Add camera into manager and start detection on newly inserted camera
            cm = CameraManager('users.sqlite')
            result = cm.add_new_camera(device_info["ip_address"], "101", True) 
            if not result:
                flash("Error inserting camera into camera manager.", "danger")
                return redirect(url_for("index"))  

            flash(message, "success" if result else "danger")
            return redirect(url_for("index", lab=lab_name))
        
        except Exception as e:
            flash("Error retrieving IP and/or device info.", "danger")
            return redirect(url_for("index"))
    
    elif is_adding_camera and not check_permission(conn, role, "add_camera"):
        flash("Admin access required to add cameras!", "error")
        return redirect(url_for("index", lab=lab_name))

    # Delete camera - ADMIN ONLY
    if is_deleting_camera and camera_name and lab_name and cam_management:
        user_id = session.get("user_id")
        dao = CameraDAO("users.sqlite")
        
        # Retrieve camera id
        id_success, camera_id = dao.get_camera_id(lab_name, camera_name, user_id)
        if not id_success:
            flash("Camera not found in database.", "danger")
            return redirect(url_for("index", lab=lab_name))
        
        # Remove camera from manager, stop detection and join threads
        camera_manager = CameraManager('users.sqlite')
        remove_success = camera_manager.remove_camera(camera_id)
        if not remove_success:
            flash("Failed to stop camera threads properly.", "danger")
            return redirect(url_for("index", lab=lab_name))
        
        # Delete camera from database
        success, message = dao.delete_camera(lab_name, camera_name, user_id)

        flash(message, "success" if success else "danger")
        return redirect(url_for("index") if success else url_for("index", lab=lab_name))
    elif is_deleting_camera and not check_permission(conn, role, "delete_camera"):
        flash("Admin access required to delete cameras!", "error")
        return redirect(url_for("index", lab=lab_name))

    if request.method == "POST" and check_permission(conn, role, "view_incompliances"):
        action = request.form.get("action")

        date_filter = request.form.get("date")
        object_filter = request.form.get("object_type")

        conn.row_factory = dict_factory
        cursor = conn.cursor()

        # Get all cameras for the dropdown
        cursor.execute("SELECT CameraId, name FROM Camera")
        cameras = cursor.fetchall()

        # Updated query to join Camera table and filter by camera name
        query = """
                SELECT s.time_generated, s.object_detected, s.confidence, s.imageURL
                FROM Snapshot s
                         LEFT JOIN Camera c ON s.camera_id = c.CameraId
                WHERE 1 = 1 \
                """
        params = []

        # Add camera filter if a camera is selected
        if camera_name:
            query += " AND c.name = ?"
            params.append(camera_name)

        if date_filter:
            query += " AND DATE(s.time_generated) = ?"
            params.append(date_filter)

        if object_filter:
            query += " AND s.object_detected = ?"
            params.append(object_filter)

        query += " ORDER BY s.time_generated DESC"

        print("Camera filter:", camera_name)
        print("Query:", query)
        print("Params:", params)

        cursor.execute(query, params)

        # Fetch all raw results from the database
        raw_results = cursor.fetchall()

        # Replace class ID with label using mapping.
        results = []
        for row in raw_results:
            time_generated = row[0]
            object_detected = row[1]
            confidence = row[2]
            image_url = row[3]

            # Try to interpret as int (e.g., if stored as string class ID)
            try:
                label = class_id_to_label.get(int(object_detected), object_detected)
            except ValueError:
                # If it's already a string label
                label = object_detected

            results.append((time_generated, label, confidence, image_url))

        conn.close()

    return render_template(
        "index.html",
        results=results,
        snapshot_folder=SNAPSHOT_FOLDER,
        lab_name=lab_name,
        camera_name=camera_name,
        cam_management=cam_management,
        user_management = user_management,
        today=today_str,
    )


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


def get_db():
    conn = sqlite3.connect('users.sqlite')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/edit_camera/<int:camera_id>', methods=['GET', 'POST'])
@login_required
@require_permission('camera_management')
def edit_camera(camera_id):

    conn = sqlite3.connect(DATABASE)
    permission_granted = check_permission(conn, session.get('role'), "camera_management")
    if not permission_granted:
        flash('No Privileges to Edit Camera', 'danger')
        return redirect(url_for('index'))
    conn.close()
    
    conn = sqlite3.connect('users.sqlite')
    conn.row_factory = dict_factory  # Enable dictionary-style access
    cursor = conn.cursor()
    
    if request.method == 'POST':
        # Handle form submission - update camera settings
        try:
            # Get form data
            name = request.form.get('name')
            resolution = int(request.form.get('resolution', 1080))
            frame_rate = int(request.form.get('frame_rate', 30))
            encoding = request.form.get('encoding', 'H.265')
            camera_ip_type = request.form.get('camera_ip_type', 'static')
            ip_address = request.form.get('ip_address')
            subnet_mask = request.form.get('subnet_mask')
            gateway = request.form.get('gateway')
            timezone = request.form.get('timezone', 'Asia/Singapore')
            sync_with_ntp = 1 if request.form.get('sync_with_ntp') else 0
            ntp_server_address = request.form.get('ntp_server_address', 'pool.ntp.org')
            manual_time = request.form.get('manual_time')
            
            # Use current time if manual_time is provided and NTP is disabled
            time_value = manual_time if manual_time and not sync_with_ntp else None
            
            # Update camera in database
            cursor.execute('''
                UPDATE Camera 
                SET name = ?, resolution = ?, frame_rate = ?, encoding = ?,
                    camera_ip_type = ?, ip_address = ?, subnet_mask = ?, gateway = ?,
                    timezone = ?, sync_with_ntp = ?, ntp_server_address = ?, time = ?
                WHERE CameraId = ?
            ''', (name, resolution, frame_rate, encoding, camera_ip_type, 
                  ip_address, subnet_mask, gateway, timezone, sync_with_ntp,
                  ntp_server_address, time_value, camera_id))
            
            conn.commit()
            flash('Camera settings updated successfully!', 'success')
            
            # Optionally, try to apply settings to actual camera via API
            try:
                apply_camera_settings(camera_id, {
                    'resolution': resolution,
                    'frame_rate': frame_rate,
                    'encoding': encoding,
                    'ip_address': ip_address,
                    'subnet_mask': subnet_mask,
                    'gateway': gateway,
                    'camera_ip_type': camera_ip_type,
                    'timezone': timezone,
                    'sync_with_ntp': sync_with_ntp,
                    'ntp_server_address': ntp_server_address
                })
                flash('Settings applied to camera successfully!', 'success')
            except Exception as e:
                flash(f'Settings saved but failed to apply to camera: {str(e)}', 'warning')
            
        except Exception as e:
            conn.rollback()
            flash(f'Error updating camera settings: {str(e)}', 'error')
        
        finally:
            conn.close()
        
        return redirect(url_for('edit_camera', camera_id=camera_id))
    
    # GET request - fetch camera data
    cursor.execute('''
        SELECT c.CameraId, c.name, c.resolution, c.frame_rate, c.encoding, 
               c.camera_ip_type, c.ip_address, c.subnet_mask, c.gateway, 
               c.timezone, c.sync_with_ntp, c.ntp_server_address, c.time, l.lab_name 
        FROM Camera c 
        JOIN Lab l ON c.camera_lab_id = l.LabId 
        WHERE c.CameraId = ?
    ''', (camera_id,))
    
    camera = cursor.fetchone()
    
    
    if not camera:
        flash('Camera not found', 'error')
        return redirect(url_for('index'))
    
    # Ensure all required fields have default values
    camera_data = {
        'CameraId': camera['CameraId'],
        'name': camera['name'] or f'Camera_{camera["CameraId"]}',
        # 'model': camera['model'] or 'Unknown',
        'resolution': camera['resolution'] or 1080,
        'frame_rate': camera['frame_rate'] or 30,
        'encoding': camera['encoding'] or 'H.265',
        'camera_ip_type': camera['camera_ip_type'] or 'static',
        'ip_address': camera['ip_address'] or '192.168.1.100',
        'subnet_mask': camera['subnet_mask'] or '255.255.255.0',
        'gateway': camera['gateway'] or '192.168.1.1',
        'timezone': camera['timezone'] or 'Asia/Singapore',
        'sync_with_ntp': camera['sync_with_ntp'] or 0,
        'ntp_server_address': camera['ntp_server_address'] or 'pool.ntp.org',
        'time': camera['time'] or '',
        'lab_name': camera['lab_name'] or 'Unknown Lab'
    }
    
    user_management = check_permission(conn, session.get('role'), "user_management")
    conn.close()
    return render_template('edit_camera.html', camera=camera_data, cam_management=permission_granted, user_management=user_management)

def apply_camera_settings(camera_id, settings):

    conn = sqlite3.connect(DATABASE)
    permission_granted = check_permission(conn, session.get('role'), "camera_management")
    if not permission_granted:
        flash('No Privileges to Edit Camera', 'danger')
        return redirect(url_for('index'))
    conn.close()

    """Apply all camera settings to the physical camera"""
    try:
        # Get camera IP address from database
        cursor = conn.cursor()
        
        cursor.execute("SELECT ip_address FROM Camera WHERE CameraId = ?", (camera_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            raise Exception(f"Camera {camera_id} not found in database")
        
        camera_ip = result[0]
        
        if not camera_ip:
            raise Exception(f"No IP address configured for camera {camera_id}")
        
        # Apply stream settings (resolution, frame rate, encoding)
        stream_settings = {k: v for k, v in settings.items() 
                          if k in ['resolution', 'frame_rate', 'encoding']}
        if stream_settings:
            apply_stream_settings(camera_ip, stream_settings)
        
        # Apply network settings (IP, subnet, gateway, IP type)
        network_settings = {k: v for k, v in settings.items() 
                           if k in ['ip_address', 'subnet_mask', 'gateway', 'camera_ip_type']}
        if network_settings:
            apply_network_settings(camera_ip, network_settings)
        
        # Apply time settings (timezone, NTP, NTP server)
        time_settings = {k: v for k, v in settings.items() 
                        if k in ['timezone', 'sync_with_ntp', 'ntp_server_address']}
        if time_settings:
            apply_time_settings(camera_ip, time_settings)
        
        print(f"✅ All settings applied to camera {camera_id} at {camera_ip}")
        
    except Exception as e:
        raise Exception(f"Failed to apply camera settings: {str(e)}")

def apply_stream_settings(camera_ip, settings):

    conn = sqlite3.connect(DATABASE)
    permission_granted = check_permission(conn, session.get('role'), "camera_management")
    if not permission_granted:
        flash('No Privileges to Edit Camera', 'danger')
        return redirect(url_for('index'))
    conn.close()

    """Apply stream settings to camera"""
    try:
        from shared.camera_discovery import CameraDiscovery
        discovery = CameraDiscovery()
        
        # Fetch current configuration
        url = f"http://{camera_ip}/ISAPI/Streaming/channels/101"
        response = requests.get(url, auth=HTTPDigestAuth(discovery.username, discovery.password))
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch current stream settings: {response.status_code}")
        
        # Parse current XML
        root = ET.fromstring(response.text)
        
        # Determine namespace and register it to avoid prefixes
        if "hikvision.com" in response.text:
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            ET.register_namespace('', ns["hik"])
        else:
            ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
            ET.register_namespace('', ns["isapi"])
        
        # Update resolution if provided
        if 'resolution' in settings:
            resolution = settings['resolution']
            if resolution == 1080:
                width, height = 1920, 1080
            elif resolution == 720:
                width, height = 1280, 720
            elif resolution == 2160:
                width, height = 3840, 2160
            elif resolution == 1520:
                width, height = 2688, 1520
            else:
                width, height = 1920, 1080
            
            # Update width and height
            if "hikvision.com" in response.text:
                width_elem = root.find(".//hik:videoResolutionWidth", namespaces=ns)
                height_elem = root.find(".//hik:videoResolutionHeight", namespaces=ns)
            else:
                width_elem = root.find(".//isapi:videoResolutionWidth", namespaces=ns)
                height_elem = root.find(".//isapi:videoResolutionHeight", namespaces=ns)
            
            if width_elem is not None:
                print(f"🔄 Changing resolution width from {width_elem.text} to {width}")
                width_elem.text = str(width)
            if height_elem is not None:
                print(f"🔄 Changing resolution height from {height_elem.text} to {height}")
                height_elem.text = str(height)
        
        # Update frame rate if provided
        if 'frame_rate' in settings:
            frame_rate = settings['frame_rate']
            # Convert to camera format (25 -> 2500)
            camera_frame_rate = frame_rate * 100
            
            if "hikvision.com" in response.text:
                framerate_elem = root.find(".//hik:maxFrameRate", namespaces=ns)
            else:
                framerate_elem = root.find(".//isapi:maxFrameRate", namespaces=ns)
            
            if framerate_elem is not None:
                print(f"🔄 Changing frame rate from {framerate_elem.text} to {camera_frame_rate}")
                framerate_elem.text = str(camera_frame_rate)
            else:
                print("❌ maxFrameRate element not found.")
        
        # Update codec if provided
        if 'encoding' in settings:
            codec = settings['encoding']
            
            if "hikvision.com" in response.text:
                codec_elem = root.find(".//hik:videoCodecType", namespaces=ns)
            else:
                codec_elem = root.find(".//isapi:videoCodecType", namespaces=ns)
            
            if codec_elem is not None:
                print(f"🔄 Changing codec from {codec_elem.text} to {codec}")
                codec_elem.text = codec
            else:
                print("❌ videoCodecType element not found.")
                return
        
        # Send updated XML back to camera
        updated_xml = ET.tostring(root, encoding="utf-8")
        headers = {"Content-Type": "application/xml"}
        
        response = requests.put(
            url,
            data=updated_xml,
            headers=headers,
            auth=HTTPDigestAuth(discovery.username, discovery.password)
        )
        
        if response.status_code == 200:
            print("✅ Stream settings updated successfully.")
        else:
            print(f"❌ Failed to update. Status: {response.status_code} - {response.reason}")
            print("Response:", response.text)
            raise Exception(f"Failed to update stream settings: {response.status_code} - {response.text}")
        
    except Exception as e:
        raise Exception(f"Failed to apply stream settings to {camera_ip}: {str(e)}")

def apply_network_settings(camera_ip, settings):

    conn = sqlite3.connect(DATABASE)
    permission_granted = check_permission(conn, session.get('role'), "camera_management")
    if not permission_granted:
        flash('No Privileges to Edit Camera', 'danger')
        return redirect(url_for('index'))
    conn.close()

    """Apply network settings to camera"""
    try:
        from shared.camera_discovery import CameraDiscovery
        discovery = CameraDiscovery()
        
        # Fetch current configuration
        url = f"http://{camera_ip}/ISAPI/System/Network/interfaces/1"
        response = requests.get(url, auth=HTTPDigestAuth(discovery.username, discovery.password))
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch current network settings: {response.status_code}")
        
        # Parse current XML
        root = ET.fromstring(response.text)
        
        # Determine namespace and register it to avoid prefixes
        if "hikvision.com" in response.text:
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            ET.register_namespace('', ns["hik"])
        else:
            ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
            ET.register_namespace('', ns["isapi"])
        
        # Update IP address type
        if 'camera_ip_type' in settings:
            addressing_type = settings['camera_ip_type']  # 'static' or 'dhcp'
            
            if "hikvision.com" in response.text:
                addressing_elem = root.find(".//hik:IPAddress/hik:addressingType", namespaces=ns)
            else:
                addressing_elem = root.find(".//isapi:IPAddress/isapi:addressingType", namespaces=ns)
            
            if addressing_elem is not None:
                print(f"🔄 Changing IP addressing type from {addressing_elem.text} to {addressing_type}")
                addressing_elem.text = addressing_type
            else:
                print("❌ addressingType element not found.")
        
        # Update static IP settings if provided
        if 'ip_address' in settings:
            ip_address = settings['ip_address']
            
            if "hikvision.com" in response.text:
                ip_elem = root.find(".//hik:IPAddress/hik:ipAddress", namespaces=ns)
            else:
                ip_elem = root.find(".//isapi:IPAddress/isapi:ipAddress", namespaces=ns)
            
            if ip_elem is not None:
                print(f"🔄 Changing IP address from {ip_elem.text} to {ip_address}")
                ip_elem.text = ip_address
            else:
                print("❌ ipAddress element not found.")
        
        if 'subnet_mask' in settings:
            subnet_mask = settings['subnet_mask']
            
            if "hikvision.com" in response.text:
                mask_elem = root.find(".//hik:IPAddress/hik:subnetMask", namespaces=ns)
            else:
                mask_elem = root.find(".//isapi:IPAddress/isapi:subnetMask", namespaces=ns)
            
            if mask_elem is not None:
                print(f"🔄 Changing subnet mask from {mask_elem.text} to {subnet_mask}")
                mask_elem.text = subnet_mask
            else:
                print("❌ subnetMask element not found.")
        
        if 'gateway' in settings:
            gateway = settings['gateway']
            
            if "hikvision.com" in response.text:
                gateway_elem = root.find(".//hik:IPAddress/hik:DefaultGateway/hik:ipAddress", namespaces=ns)
            else:
                gateway_elem = root.find(".//isapi:IPAddress/isapi:DefaultGateway/isapi:ipAddress", namespaces=ns)
            
            if gateway_elem is not None:
                print(f"🔄 Changing gateway from {gateway_elem.text} to {gateway}")
                gateway_elem.text = gateway
            else:
                print("❌ DefaultGateway ipAddress element not found.")
        
        # Send updated XML back to camera
        updated_xml = ET.tostring(root, encoding="utf-8")
        headers = {"Content-Type": "application/xml"}
        
        response = requests.put(
            url,
            data=updated_xml,
            headers=headers,
            auth=HTTPDigestAuth(discovery.username, discovery.password)
        )
        
        if response.status_code == 200:
            print("✅ Network settings updated successfully.")
        else:
            print(f"❌ Failed to update network settings. Status: {response.status_code} - {response.reason}")
            print("Response:", response.text)
            raise Exception(f"Failed to update network settings: {response.status_code} - {response.text}")
        
    except Exception as e:
        raise Exception(f"Failed to apply network settings to {camera_ip}: {str(e)}")

def apply_time_settings(camera_ip, settings):

    conn = sqlite3.connect(DATABASE)
    permission_granted = check_permission(conn, session.get('role'), "camera_management")
    if not permission_granted:
        flash('No Privileges to Edit Camera', 'danger')
        return redirect(url_for('index'))
    conn.close()

    """Apply time settings to camera"""
    try:
        from shared.camera_discovery import CameraDiscovery
        discovery = CameraDiscovery()
        
        # Update time configuration
        time_url = f"http://{camera_ip}/ISAPI/System/time"
        response = requests.get(time_url, auth=HTTPDigestAuth(discovery.username, discovery.password))
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch current time settings: {response.status_code}")
        
        # Parse current XML
        root = ET.fromstring(response.text)
        
        # Determine namespace and register it to avoid prefixes
        if "hikvision.com" in response.text:
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            ET.register_namespace('', ns["hik"])
        else:
            ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
            ET.register_namespace('', ns["isapi"])
        
        # Update time mode based on NTP setting
        if 'sync_with_ntp' in settings:
            sync_with_ntp = settings['sync_with_ntp']
            time_mode = 'NTP' if sync_with_ntp else 'manual'
            
            if "hikvision.com" in response.text:
                time_mode_elem = root.find(".//hik:timeMode", namespaces=ns)
            else:
                time_mode_elem = root.find(".//isapi:timeMode", namespaces=ns)
            
            if time_mode_elem is not None:
                print(f"🔄 Changing time mode from {time_mode_elem.text} to {time_mode}")
                time_mode_elem.text = time_mode
            else:
                print("❌ timeMode element not found.")
        
        # Update timezone if provided
        if 'timezone' in settings:
            timezone = settings['timezone']
            # Convert timezone to camera format
            if timezone == 'Asia/Singapore':
                tz_value = 'CST-8:00:00'
            elif timezone == 'UTC':
                tz_value = 'UTC+00:00'
            else:
                tz_value = 'CST-8:00:00'  # default
            
            if "hikvision.com" in response.text:
                timezone_elem = root.find(".//hik:timeZone", namespaces=ns)
            else:
                timezone_elem = root.find(".//isapi:timeZone", namespaces=ns)
            
            if timezone_elem is not None:
                print(f"🔄 Changing timezone from {timezone_elem.text} to {tz_value}")
                timezone_elem.text = tz_value
            else:
                print("❌ timeZone element not found.")
        
        # Send updated time XML back to camera
        updated_xml = ET.tostring(root, encoding="utf-8")
        headers = {"Content-Type": "application/xml"}
        
        response = requests.put(
            time_url,
            data=updated_xml,
            headers=headers,
            auth=HTTPDigestAuth(discovery.username, discovery.password)
        )
        
        if response.status_code == 200:
            print("✅ Time settings updated successfully.")
        else:
            print(f"❌ Failed to update time settings. Status: {response.status_code} - {response.reason}")
            print("Response:", response.text)
            raise Exception(f"Failed to update time settings: {response.status_code} - {response.text}")
        
        # Update NTP server if provided
        if 'ntp_server_address' in settings:
            ntp_url = f"http://{camera_ip}/ISAPI/System/time/ntpServers"
            response = requests.get(ntp_url, auth=HTTPDigestAuth(discovery.username, discovery.password))
            
            if response.status_code == 200:
                ntp_root = ET.fromstring(response.text)
                
                # Register namespace for NTP XML
                if "hikvision.com" in response.text:
                    ET.register_namespace('', ns["hik"])
                    hostname_elem = ntp_root.find(".//hik:NTPServer/hik:hostName", namespaces=ns)
                else:
                    ET.register_namespace('', ns["isapi"])
                    hostname_elem = ntp_root.find(".//isapi:NTPServer/isapi:hostName", namespaces=ns)
                
                if hostname_elem is not None:
                    print(f"🔄 Changing NTP server from {hostname_elem.text} to {settings['ntp_server_address']}")
                    hostname_elem.text = settings['ntp_server_address']
                    
                    # Send updated NTP XML back to camera
                    updated_ntp_xml = ET.tostring(ntp_root, encoding="utf-8")
                    
                    response = requests.put(
                        ntp_url,
                        data=updated_ntp_xml,
                        headers=headers,
                        auth=HTTPDigestAuth(discovery.username, discovery.password)
                    )
                    
                    if response.status_code == 200:
                        print("✅ NTP server updated successfully.")
                    else:
                        print(f"❌ Failed to update NTP server. Status: {response.status_code} - {response.reason}")
                        print("Response:", response.text)
                else:
                    print("❌ NTP hostName element not found.")
            else:
                print(f"❌ Failed to fetch NTP settings. Status: {response.status_code}")
        
    except Exception as e:
        raise Exception(f"Failed to apply time settings to {camera_ip}: {str(e)}")

@app.route('/video_feed/<camera_id>')
def video_feed(camera_id):

    conn = sqlite3.connect(DATABASE)
    role = session.get('role')
    if not check_permission(conn, role, "video_feed"):
        flash('No Privileges to View Live Video Feed', 'danger')
        return redirect(url_for('index'))
    conn.close()
    
    cam_manager = CameraManager.get_instance()

    camera_id = int(camera_id)
    if camera_id not in cam_manager.camera_pool:
        return f"Camera {camera_id} not found.", 404

    camera = cam_manager.camera_pool[camera_id]["camera"]
    print(f"[STREAM] Client connected to /video_feed/{camera_id}")

    def generate_stream():
        while camera.running:
            try:
                frame = (camera.display_queue).get(timeout=1)
            except queue.Empty:
                continue

            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue

            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/check_ip', methods=['POST'])
def check_ip():
    ip_address = request.json.get('ip')

    cd = CameraDiscovery()
    discover_results = cd.discover_camera(ip_address)
    if discover_results is None:
        return jsonify({'valid': False, 'device_info': discover_results})

    return jsonify({'valid': True, 'device_info': discover_results})

@app.route('/add_camera', methods=['POST'])
@login_required
@require_permission('camera_management')
def add_camera():
    try:
        data = request.get_json()
        camera_ip = data.get('ip')
        device_info = data.get('device_info')
        
        print(f"🔍 Attempting to add camera: {camera_ip}")
        print(f"📋 Device info: {device_info}")
        
        # Check if camera already exists
        conn = sqlite3.connect('users.sqlite')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Camera WHERE ip_address = ?", (camera_ip,))
        if cursor.fetchone()[0] > 0:
            print(f"❌ Camera {camera_ip} already exists in database")
            conn.close()
            return jsonify({'success': False, 'message': f'Camera {camera_ip} already exists!'})
        
        # Get default lab ID
        cursor.execute("SELECT LabId FROM Lab LIMIT 1")
        lab_result = cursor.fetchone()
        lab_id = lab_result[0] if lab_result else 1
        
        # Get current user ID from session
        user_id = session.get('user_id', 1)
        
        # Add to database with correct column names and all required fields
        cursor.execute("""
            INSERT INTO Camera (name, ip_address, camera_lab_id, camera_user_id, resolution, frame_rate, encoding,
                              subnet_mask, gateway, camera_ip_type, timezone, sync_with_ntp, ntp_server_address, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            device_info.get('device_name', f'Camera_{camera_ip}'),
            camera_ip,
            lab_id,  # Fixed: using camera_lab_id column name
            user_id,  # Added: camera_user_id is required
            device_info.get('resolution', 1080),
            device_info.get('frame_rate', 25),
            device_info.get('encoding', 'H.265'),
            device_info.get('subnet_mask', '255.255.255.0'),
            device_info.get('gateway', '192.168.1.1'),
            device_info.get('camera_ip_type', 'static'),
            device_info.get('timezone', 'Asia/Singapore'),
            device_info.get('sync_with_ntp', 1 if device_info.get('sync_with_ntp') else 0),
            device_info.get('ntp_server_address', 'pool.ntp.org'),  # Fixed: use correct key
            device_info.get('time', '2025-01-01T00:00:00')  # Added: time is required (NOT NULL)
        ))
        
        camera_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ Camera {camera_ip} added to database with ID {camera_id}")
        
        # Add to camera manager
        from shared.camera_manager import CameraManager
        # Try to get existing instance first (singleton pattern)
        manager = CameraManager.get_instance()
        # except RuntimeError:
        #     # If no instance exists, create one with db_path
        #     manager = CameraManager('users.sqlite')
        manager.add_new_camera(camera_id, camera_ip, "101", True)
        
        print(f"✅ Camera {camera_ip} added to camera manager")
        
        return jsonify({'success': True, 'message': f'Camera {camera_ip} added successfully!'})
        
    except Exception as e:
        print(f"❌ Error adding camera: {e}")
        return jsonify({'success': False, 'message': f'Error adding camera: {str(e)}'})

@app.route('/user_management', methods=['GET', 'POST'])
@login_required
@require_permission('user_management')
def user_management():
    
    # Open database connection from permission verification
    try:
        conn = sqlite3.connect(DATABASE)
    except Exception:
        return redirect(url_for("index"))
    role = session.get('role')
    if role is None:
        return redirect(url_for("index"))
    
    cam_management = check_permission(conn, role, "camera_management")
    user_management = check_permission(conn, role, "user_management")

    users = get_all_users()
    roles = get_all_roles()

    if request.method == "GET":
        return render_template(
            "user_management.html",
            users=users,
            roles=roles,
            cam_management=cam_management,
            user_management=user_management,
        )

    if request.method == "POST":
        user_id = request.form.get("user_id")
        new_role = request.form.get("new_role")
        update = request.args.get("update")
        delete = request.args.get("delete")

        if int(delete) and not int(update):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            flash("User role updated successfully.", "success")

        elif int(update) and not int(delete):
            print(new_role)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Roles WHERE name = ?", (new_role,))
            role_exists = cursor.fetchone()
            if role_exists:
                cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
                conn.commit()
                flash("User role updated successfully.", "success")
        else:
            flash("Missing user or role data.", "danger")

        return redirect(url_for("user_management"))

@app.route('/role_management', methods=['GET', 'POST'])
@login_required
@require_permission('user_management')
def role_management():

    # Open database connection from permission verification
    try:
        conn = sqlite3.connect(DATABASE)
    except Exception:
        return redirect(url_for("index"))
    role = session.get('role')
    if role is None:
        return redirect(url_for("index"))
    
    cam_management = check_permission(conn, role, "camera_management")
    user_management = check_permission(conn, role, "user_management")

    roles = get_all_roles()
    permissions = get_all_permissions()
    role_permissions = get_all_rolepermissions()

    return render_template(
        'role_management.html',
        roles=roles,
        permissions=permissions,
        role_permissions=role_permissions,
        cam_management=cam_management,
        user_management=user_management
    )
    
@app.route('/create_account', methods=['GET', 'POST'])
@login_required
@require_permission('user_management')
def create_account():

    # Open database connection from permission verification
    try:
        conn = sqlite3.connect(DATABASE)
    except Exception:
        return redirect(url_for("index"))
    role = session.get('role')
    if role is None:
        return redirect(url_for("index"))
    
    cam_management = check_permission(conn, role, "camera_management")
    user_management = check_permission(conn, role, "user_management")

    roles = get_all_roles()

    if request.method == "POST":
        # TODO: Add logic to create new account
        return redirect(url_for("create_account.html"))
    

    return render_template("create_account.html", roles=roles, cam_management=cam_management, user_management=user_management,)