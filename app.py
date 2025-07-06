from flask import Flask, request, session, redirect, url_for, render_template, flash
from functools import wraps
from database import init_database, create_default_admin, verify_user, update_last_login, \
    create_default_labs_and_cameras, create_camera
import sqlite3
import os
import secrets
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

DATABASE = "detections.sqlite"
SNAPSHOT_FOLDER = "snapshots"


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

    return dict(labs=list(labs.values()))


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

    is_editing_camera = request.args.get("edit", "0") == "1"
    is_deleting_camera = request.args.get("delete", "0") == "1"
    is_adding_camera = request.args.get("add", "0") == "1"
    today_str = datetime.now().strftime('%Y-%m-%dT%H:%M')

    is_admin = session.get('role') == 'admin'

    results = []

    # Create default camera inside the database.
    if is_adding_camera and lab_name:
        user_id = session.get("user_id")

        # Get the Lab_id based on Lab_name
        conn = sqlite3.connect("users.sqlite")
        cursor = conn.cursor()
        cursor.execute("SELECT LabId FROM Lab WHERE lab_name = ?", (lab_name,))
        lab_row = cursor.fetchone()
        conn.close()

        if not lab_row:
            flash("Lab not found.", "danger")
            return redirect(url_for("index"))

        lab_id = lab_row[0]

        # Generate a default name like "Camera 1", "Camera 2".
        conn = sqlite3.connect("users.sqlite")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Camera WHERE camera_lab_id = ?", (lab_id,))
        camera_count = cursor.fetchone()[0]
        conn.close()

        default_name = f"Camera {camera_count + 1}"

        # Call your existing function with only required args
        success = create_camera(
            name=default_name,
            camera_user_id=user_id,
            camera_lab_id=lab_id,
        )

        if success:
            flash(f"{default_name} added to {lab_name}.", "success")
        else:
            flash("Failed to add camera.", "danger")

        return redirect(url_for("index", lab=lab_name))

    if is_deleting_camera and camera_name and lab_name:
        user_id = session.get("user_id")

        conn = sqlite3.connect("users.sqlite")
        cursor = conn.cursor()

        # Get lab_id for the lab_name
        cursor.execute("SELECT LabId FROM Lab WHERE lab_name = ?", (lab_name,))
        lab_row = cursor.fetchone()
        if not lab_row:
            flash("Lab not found.", "danger")
            conn.close()
            return redirect(url_for("index"))

        lab_id = lab_row[0]

        # Delete camera by name, Lab_id, and optionally user_id (for security)
        cursor.execute("""
                       DELETE
                       FROM Camera
                       WHERE name = ?
                         AND camera_lab_id = ?
                         AND camera_user_id = ?
                       """, (camera_name, lab_id, user_id))
        conn.commit()
        affected_rows = cursor.rowcount
        conn.close()

        if affected_rows > 0:
            flash(f"Camera '{camera_name}' deleted successfully.", "success")
        else:
            flash(f"Failed to delete camera '{camera_name}'.", "danger")

        return redirect(url_for("index", lab=lab_name))

    if request.method == "POST":
        action = request.form.get("action")

        date_filter = request.form.get("date")
        object_filter = request.form.get("object_type")

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        query = "SELECT timestamp, object_type, confidence, image_path FROM detections WHERE 1=1"
        params = []

        if date_filter:
            query += " AND DATE(timestamp) = ?"
            params.append(date_filter)

        if object_filter:
            query += " AND object_type = ?"
            params.append(object_filter)

        cursor.execute(query, params)
        results = cursor.fetchall()
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

        return redirect(url_for('index'))  # or return to camera page

    # GET: fetch camera settings and labs for sidebar
    cursor.execute('SELECT * FROM Camera WHERE CameraId=?', (camera_id,))
    camera = cursor.fetchone()
    cursor.execute('SELECT * FROM Lab')  # for lab list/sidebar
    labs = cursor.fetchall()
    conn.close()
    return render_template('edit_camera.html', camera=camera)


if __name__ == "__main__":
    init_database()
    create_default_admin()
    create_default_labs_and_cameras()
    app.run(debug=True)
