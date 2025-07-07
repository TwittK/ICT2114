from flask import Flask, request, session, redirect, url_for, render_template, flash
from functools import wraps

from data_source.camera_dao import CameraDAO
from database import init_database, create_default_admin, verify_user, update_last_login, \
    create_default_labs_and_cameras, create_camera
import sqlite3
import os
import secrets
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

DATABASE = "users.sqlite"
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

    is_deleting_camera = request.args.get("delete", "0") == "1"
    is_adding_camera = request.args.get("add", "0") == "1"
    today_str = datetime.now().strftime('%Y-%m-%dT%H:%M')

    is_admin = session.get('role') == 'admin'

    results = []

    # Create default camera inside the database.
    if is_adding_camera and lab_name:
        user_id = session.get("user_id")
        dao = CameraDAO("users.sqlite")

        success, message = dao.add_default_camera(lab_name, user_id)
        flash(message, "success" if success else "danger")
        return redirect(url_for("index", lab=lab_name))

    if is_deleting_camera and camera_name and lab_name:
        user_id = session.get("user_id")
        dao = CameraDAO("users.sqlite")

        success, message = dao.delete_camera(lab_name, camera_name, user_id)

        flash(message, "success" if success else "danger")
        return redirect(url_for("index", lab=lab_name))

    if request.method == "POST":
        action = request.form.get("action")

        date_filter = request.form.get("date")
        object_filter = request.form.get("object_type")

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        query = "SELECT time_generated, object_detected, confidence, imageURL FROM Snapshot WHERE 1=1"
        params = []

        if date_filter:
            query += " AND DATE(time_generated) = ?"
            params.append(date_filter)

        if object_filter:
            query += " AND object_detected = ?"
            params.append(object_filter)
            
        print("results", results)

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
