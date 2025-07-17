from flask import Flask, request, session, redirect, url_for, render_template, flash, Response
from functools import wraps
from data_source.camera_dao import CameraDAO
from datetime import datetime
import sqlite3

import cv2
from database import verify_user, update_last_login
from shared.camera_manager import CameraManager
import queue

DATABASE = "users.sqlite"
SNAPSHOT_FOLDER = "snapshots"

app = Flask(__name__)

class_id_to_label = {
    39: "Bottle",
    40: "Wine Glass",
    41: "Cup",
}


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or session.get('role') != 'admin':
            flash('Admin access required!', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


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
    today_str = datetime.now().strftime('%Y-%m-%dT%H:%M')

    is_admin = session.get('role') == 'admin'

    results = []

    # Create default camera inside the database - ADMIN ONLY
    if is_adding_camera and lab_name and is_admin:
        user_id = session.get("user_id")
        dao = CameraDAO("users.sqlite")

        success, message = dao.add_default_camera(lab_name, user_id)
        flash(message, "success" if success else "danger")
        return redirect(url_for("index", lab=lab_name))
    elif is_adding_camera and not is_admin:
        flash("Admin access required to add cameras!", "error")
        return redirect(url_for("index", lab=lab_name))

    # Delete camera - ADMIN ONLY
    if is_deleting_camera and camera_name and lab_name and is_admin:
        user_id = session.get("user_id")
        dao = CameraDAO("users.sqlite")

        success, message = dao.delete_camera(lab_name, camera_name, user_id)

        flash(message, "success" if success else "danger")
        return redirect(url_for("index", lab=lab_name))
    elif is_deleting_camera and not is_admin:
        flash("Admin access required to delete cameras!", "error")
        return redirect(url_for("index", lab=lab_name))

    if request.method == "POST":
        action = request.form.get("action")

        date_filter = request.form.get("date")
        object_filter = request.form.get("object_type")

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

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
        is_admin=is_admin,
        today=today_str,
    )


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    return render_template('admin.html')


def get_db():
    conn = sqlite3.connect('users.sqlite')
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/camera/<int:camera_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_camera(camera_id):
    conn = get_db()
    cursor = conn.cursor()

    camera_name = request.args.get("camera")
    lab_name = request.args.get("lab")
    if camera_name and lab_name:
        session['selected_camera'] = {
            'name': camera_name,
            'lab': lab_name
        }

    print("Session - selected camera:", session.get('selected_camera'))

    if request.method == 'POST':
        # Grab form data
        name = request.form['name']
        resolution = request.form['resolution']
        frame_rate = request.form['frame_rate']
        encoding = request.form['encoding']
        ip_type = request.form['camera_ip_type']
        ip_addr = request.form['ip_address']
        subnet = request.form['subnet_mask']
        gateway = request.form['gateway']
        timezone = request.form['timezone']
        sync = int(request.form.get('sync_with_ntp', 0))
        ntp = request.form['ntp_server_address']
        time = request.form['manual_time']

        cursor.execute('''
                       UPDATE Camera
                       SET name=?,
                           resolution=?,
                           frame_rate=?,
                           encoding=?,
                           camera_ip_type=?,
                           ip_address=?,
                           subnet_mask=?,
                           gateway=?,
                           timezone=?,
                           sync_with_ntp=?,
                           ntp_server_address=?,
                           time=?
                       WHERE CameraId = ?
                       ''', (name, resolution, frame_rate, encoding, ip_type, ip_addr,
                             subnet, gateway, timezone, sync, ntp, time, camera_id))
        conn.commit()

        flash('Camera settings updated successfully!', 'success')
        return redirect(url_for('index'))

    # GET: fetch camera settings and labs for sidebar
    cursor.execute('SELECT * FROM Camera WHERE CameraId=?', (camera_id,))
    camera = cursor.fetchone()

    if not camera:
        flash('Camera not found!', 'error')
        return redirect(url_for('index'))

    cursor.execute('SELECT * FROM Lab')  # for lab list/sidebar
    labs = cursor.fetchall()
    conn.close()
    return render_template('edit_camera.html', camera=camera)


@app.route('/video_feed/<camera_id>')
def video_feed(camera_id):
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
