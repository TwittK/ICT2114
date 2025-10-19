import logging
import math
import queue
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from functools import wraps
import pytz

import cv2
import os
import psycopg2
import requests
from data_source.camera_dao import CameraDAO
from data_source.class_labels import ClassLabelRepository
from data_source.lab_dao import LabDAO
from data_source.role_dao import RoleDAO
from data_source.user_dao import UserDAO
from database import (
    verify_user,
    update_last_login,
    get_all_users,
    get_incompliance_details_for_video,
)
from dotenv import load_dotenv
from flask import (
    Flask,
    request,
    session,
    redirect,
    url_for,
    render_template,
    flash,
    Response,
    jsonify,
)
from psycopg2.extras import RealDictCursor
from requests.auth import HTTPDigestAuth
from shared.camera_discovery import CameraDiscovery
from shared.camera_manager import CameraManager
from threads.nvr import NVR
from web.utils import (
    check_permission,
    validate_and_sanitize_text,
    require_permission,
    login_required,
)
from werkzeug.security import generate_password_hash

from shared.mqtt_client import MQTTClient

from shared.config import LF_CAMERA_PER_PAGE

# Silence Watchdog debug spam.
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.basicConfig(level=logging.DEBUG)

# Load environment variables from .env
load_dotenv()
DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}
SNAPSHOT_FOLDER = "snapshots"
NO_PRIVILEGES = "Not enough privileges to complete action"

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

label_repo = ClassLabelRepository()
mqtt_client = MQTTClient()


# def dict_factory(cursor, row):
#     """Convert sqlite3.Row to dictionary"""
#     d = {}
#     for idx, col in enumerate(cursor.description):
#         d[col[0]] = row[idx]
#     return d


@app.context_processor
def inject_labs_with_cameras():
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT l.LabId,
               l.lab_name,
               c.CameraId,
               c.name
        FROM Lab l
                 LEFT JOIN Camera c ON c.camera_lab_id = l.LabId
        ORDER BY l.lab_name ASC, c.name ASC
        """
    )

    rows = cursor.fetchall()
    conn.close()

    # Group cameras under their labs.
    labs = {}
    for lab_id, lab_name, camera_id, camera_name in rows:
        if lab_id not in labs:
            labs[lab_id] = {"lab_id": lab_id, "lab_name": lab_name, "cameras": []}
        # Might be None if no camera exists.
        if camera_id:
            labs[lab_id]["cameras"].append(
                {
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                }
            )

    # Ensure all labs have a 'cameras' key, at least empty list.
    for lab in labs.values():
        if "cameras" not in lab or lab["cameras"] is None:
            lab["cameras"] = []

    return dict(labs=list(labs.values()))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = verify_user(email, password)

        if user:
            session["logged_in"] = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["email"] = user["email"]
            session["role"] = user["role"]

            update_last_login(user["id"])

            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password!", "danger")

    return render_template("login.html")


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    # Open DB connection to fetch valid labs and cameras
    conn = psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    # Get all lab names
    cursor.execute("SELECT lab_name FROM Lab ORDER BY lab_name")
    all_labs = [row["lab_name"] for row in cursor.fetchall()]
    default_lab = (
        "E2-L6-016" if "E2-L6-016" in all_labs else (all_labs[0] if all_labs else None)
    )

    # Get lab from query or fallback
    lab_name = request.args.get("lab")
    if lab_name not in all_labs:
        lab_name = default_lab

    # Pagination parameters
    try:
        current_page = int(request.args.get("page", 1))
        if current_page < 1:
            current_page = 1
    except ValueError:
        current_page = 1

    # Cameras per page
    per_page = LF_CAMERA_PER_PAGE
    offset = (current_page - 1) * per_page

    # Get all cameras in this lab with their IDs for live feed
    cameras = []
    total_pages = 0
    if lab_name:
        # Get total number of cameras for pagination.
        cursor.execute("""
            SELECT COUNT(*) FROM Camera c
            JOIN Lab l ON c.camera_lab_id = l.LabId
            WHERE l.lab_name = %s
        """, (lab_name,), )

        total_cameras = cursor.fetchone()["count"]
        total_pages = math.ceil(total_cameras / per_page)

        # Get paginated cameras
        cursor.execute("""
            SELECT c.CameraId as camera_id, c.name
            FROM Camera c
            JOIN Lab l ON c.camera_lab_id = l.LabId
            WHERE l.lab_name = %s
            ORDER BY c.name
            LIMIT %s OFFSET %s
        """, (lab_name, per_page, offset), )
        cameras = cursor.fetchall()

    conn.close()

    # Handle camera deletion (admin only)
    is_deleting_camera = request.args.get("delete", "0") == "1"
    camera_name = request.args.get("camera")

    role = session.get("role")
    if role is None:
        return redirect(url_for("login"))

    cam_management = check_permission(role, "camera_management")
    user_role_management = check_permission(role, "user_role_management")

    # Delete camera - ADMIN ONLY
    if is_deleting_camera and camera_name and lab_name and cam_management:
        user_id = session.get("user_id")
        dao = CameraDAO(DB_PARAMS)

        # Retrieve camera id
        id_success, camera_id = dao.get_camera_id(lab_name, camera_name, user_id)
        if not id_success:
            flash("Camera not found in database.", "danger")
            return redirect(url_for("index", lab=lab_name))

        # Remove camera from manager
        camera_manager = CameraManager(DB_PARAMS)
        remove_success = camera_manager.remove_camera(camera_id)
        if not remove_success:
            flash("Failed to stop camera threads properly.", "danger")
            return redirect(url_for("index", lab=lab_name))

        # Delete camera from database
        success, message = dao.delete_camera(lab_name, camera_name, user_id)
        flash(message, "success" if success else "danger")
        return redirect(url_for("index", lab=lab_name))
    elif is_deleting_camera and not cam_management:
        flash("Admin access required to delete cameras!", "danger")
        return redirect(url_for("index", lab=lab_name))

    return render_template(
        "index.html",
        lab_name=lab_name,
        cameras=cameras,
        cam_management=cam_management,
        user_role_management=user_role_management,
        current_page=current_page,
        total_pages=total_pages,
    )


@app.route("/second-incompliance", methods=["GET", "POST"])
@login_required
def second_incompliance():
    lab_dao = LabDAO(DB_PARAMS)
    camera_dao = CameraDAO(DB_PARAMS)
    # Get lab and camera from URL query parameters - mandatory for filtering
    lab_name = request.args.get("lab")
    camera_name = request.args.get("camera")

    # Current page number from query params, default to 1
    current_page = request.args.get("page", default=1, type=int)
    # Number of results per page.
    page_size = 9

    # Redirect if either lab or camera not specified.
    if not lab_name or not camera_name:
        try:
            all_labs = lab_dao.get_all_labs() or []
            if all_labs:
                # First lab
                lab_name = all_labs[0]["lab_name"]
            else:
                lab_name = None

            camera_name = camera_dao.get_first_cameras_for_lab(lab_name)
        except Exception:
            flash("Error retrieving default lab and camera.", "danger")
            return redirect(url_for("index"))

        if lab_name and camera_name:
            # Redirect with default parameters so page loads correctly.
            return redirect(
                url_for("second_incompliance", lab=lab_name, camera=camera_name)
            )
        else:
            flash("No labs or cameras configured.", "danger")
            return redirect(url_for("index"))

    # Get filters from POST form or use defaults
    if request.method == "POST":
        selected_date = request.form.get("date", "")
        selected_object_type = request.form.get("object_type", "")
    else:
        # On GET request, use empty filters to show all results
        selected_date = ""
        selected_object_type = ""

    # Retrieve all labels for dropdown
    all_labels = label_repo.get_all_labels()

    # User role and camera management
    cam_management = None
    user_role_management = None

    results = []

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        conn = psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Check user permission to view incompliances
        role = session.get("role")
        if role is None or not check_permission(role, "view_incompliances"):
            flash("Permission denied to view incompliances.", "danger")
            return redirect(url_for("index"))

        cam_management = check_permission(role, "camera_management")
        user_role_management = check_permission(role, "user_role_management")

        # Fetch list of all labs for dropdown
        cursor.execute("SELECT lab_name FROM Lab ORDER BY lab_name")
        all_labs = [row["lab_name"] for row in cursor.fetchall()]

        # Fetch cameras only for the selected lab.
        cursor.execute(
            """
            SELECT c.name
            FROM Camera c
                     JOIN Lab l ON c.camera_lab_id = l.LabId
            WHERE l.lab_name = %s
            ORDER BY c.name
            """,
            (lab_name,),
        )

        all_cameras = [row["name"] for row in cursor.fetchall()]

        # SQL query to find repeated incompliances for specific lab and camera
        # MOVED OUTSIDE OF if request.method == "POST" block
        query = """
                SELECT s.DetectionId, s.time_generated, s.object_detected, s.confidence, s.imageURL
                FROM Snapshot s
                         JOIN (SELECT person_id, MIN(time_generated) AS first_time
                               FROM Snapshot
                               WHERE person_id IS NOT NULL
                               GROUP BY person_id
                               HAVING COUNT(*) > 1) repeats
                              ON s.person_id = repeats.person_id
                WHERE s.time_generated > repeats.first_time
                  AND EXISTS(SELECT 1
                             FROM Camera c
                                      JOIN Lab l ON c.camera_lab_id = l.LabId
                             WHERE c.CameraId = s.camera_id
                               AND l.lab_name = %s
                               AND c.name = %s) \
                """

        params = [lab_name, camera_name]

        # Apply date filter if selected.
        if selected_date:
            query += " AND DATE(s.time_generated) = %s"
            params.append(selected_date)

        # Apply object type filter if selected.
        if selected_object_type:
            if selected_object_type == "food":
                food_ids = label_repo.get_food_class_ids()
                # Convert IDs to strings for the query
                food_ids_str = [str(fid) for fid in food_ids]
                placeholders = ",".join("%s" for _ in food_ids_str)
                query += f" AND s.object_detected IN ({placeholders})"
                params.extend(food_ids_str)
            elif selected_object_type == "drink":
                drinks_ids = label_repo.get_drink_class_ids()
                # Convert IDs to strings for the query
                drinks_ids_str = [str(did) for did in drinks_ids]
                placeholders = ",".join("%s" for _ in drinks_ids_str)
                query += f" AND s.object_detected IN ({placeholders})"
                params.extend(drinks_ids_str)
            else:
                # Assume it's a specific class ID
                query += " AND s.object_detected = %s"
                params.append(selected_object_type)

        query += " ORDER BY s.time_generated DESC"

        cursor.execute(query, params)
        raw_results = cursor.fetchall()

        # Process results: replace class ID with label.
        for row in raw_results:
            detection_id = row["detectionid"]
            time_generated = row["time_generated"]
            object_detected = row["object_detected"]
            confidence = row["confidence"]
            image_url = row["imageurl"]

            try:
                label = label_repo.get_label(int(object_detected))
            except (ValueError, TypeError):
                label = object_detected

            results.append((detection_id, time_generated, label, confidence, image_url))

        conn.close()

    except Exception as e:
        flash("Error loading second incompliance data.", "danger")
        print(f"Exception: {e}")
        return redirect(url_for("index"))

    # Total results
    total_results = len(results)
    # Compute total pages based on page size.
    total_pages = max(1, math.ceil(total_results / page_size))

    # Slice results for the current page.
    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size
    results_page = results[start_index:end_index]

    return render_template(
        "second_incompliance.html",
        results=results_page,
        lab_name=lab_name,
        camera_name=camera_name,
        cam_management=cam_management,
        user_role_management=user_role_management,
        all_labs=all_labs,
        all_cameras=all_cameras,
        all_labels=all_labels,
        selected_date=selected_date,
        selected_object_type=selected_object_type,
        current_page=current_page,
        total_pages=total_pages,
    )


@app.route("/all-incompliance", methods=["GET", "POST"])
@login_required
def all_incompliance():
    lab_dao = LabDAO(DB_PARAMS)
    camera_dao = CameraDAO(DB_PARAMS)

    # Get lab and camera from URL query parameters
    lab_name = request.args.get("lab")
    camera_name = request.args.get("camera")

    # Current page number from query params, default to 1
    current_page = request.args.get("page", default=1, type=int)
    # Number of results per page
    page_size = 9

    # Redirect if either lab or camera not specified
    if not lab_name or not camera_name:
        try:
            all_labs = lab_dao.get_all_labs() or []
            if all_labs:
                lab_name = all_labs[0]["lab_name"]
            else:
                lab_name = None

            camera_name = camera_dao.get_first_cameras_for_lab(lab_name)
        except Exception:
            flash("Error retrieving default lab and camera.", "danger")
            return redirect(url_for("index"))

        if lab_name and camera_name:
            return redirect(
                url_for("all_incompliance", lab=lab_name, camera=camera_name)
            )
        else:
            flash("No labs or cameras configured.", "danger")
            return redirect(url_for("index"))

    # Get filters from POST form or use defaults
    if request.method == "POST":
        selected_date = request.form.get("date", "")
        selected_object_type = request.form.get("object_type", "")
    else:
        # On GET request, use empty filters to show all results
        selected_date = ""
        selected_object_type = ""

    # Retrieve all labels for dropdown
    all_labels = label_repo.get_all_labels()

    # User role and camera management
    role = session.get("role")
    if role is None or not check_permission(role, "view_incompliances"):
        flash("Permission denied to view incompliances.", "danger")
        return redirect(url_for("index"))

    cam_management = check_permission(role, "camera_management")
    user_role_management = check_permission(role, "user_role_management")

    results = []

    try:
        conn = psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)
        cursor = conn.cursor()

        # Fetch list of all labs for dropdown
        cursor.execute("SELECT lab_name FROM Lab ORDER BY lab_name")
        all_labs = [row["lab_name"] for row in cursor.fetchall()]

        # Fetch cameras only for the selected lab
        cursor.execute(
            """
            SELECT c.name
            FROM Camera c
            JOIN Lab l ON c.camera_lab_id = l.LabId
            WHERE l.lab_name = %s
            ORDER BY c.name
            """,
            (lab_name,),
        )
        all_cameras = [row["name"] for row in cursor.fetchall()]

        # THIS IS THE KEY CHANGE - Query runs on BOTH GET and POST
        # SQL query to find all incompliances for specific lab and camera
        query = """
            SELECT s.DetectionId, s.time_generated, s.object_detected, s.confidence, s.imageURL
            FROM Snapshot s
            JOIN Camera c ON s.camera_id = c.CameraId
            JOIN Lab l ON c.camera_lab_id = l.LabId
            WHERE l.lab_name = %s AND c.name = %s
        """
        params = [lab_name, camera_name]

        # Apply date filter if selected
        if selected_date:
            query += " AND DATE(s.time_generated) = %s"
            params.append(selected_date)

        # Apply object type filter if selected.
        if selected_object_type:
            if selected_object_type == "food":
                food_ids = label_repo.get_food_class_ids()
                # Convert IDs to strings for the query
                food_ids_str = [str(fid) for fid in food_ids]
                placeholders = ",".join("%s" for _ in food_ids_str)
                query += f" AND s.object_detected IN ({placeholders})"
                params.extend(food_ids_str)
            elif selected_object_type == "drink":
                drinks_ids = label_repo.get_drink_class_ids()
                # Convert IDs to strings for the query
                drinks_ids_str = [str(did) for did in drinks_ids]
                placeholders = ",".join("%s" for _ in drinks_ids_str)
                query += f" AND s.object_detected IN ({placeholders})"
                params.extend(drinks_ids_str)
            else:
                # Assume it's a specific class ID
                query += " AND s.object_detected = %s"
                params.append(selected_object_type)

        query += " ORDER BY s.time_generated DESC"

        print(f"[DEBUG] Executing query with lab={lab_name}, camera={camera_name}")
        print(f"[DEBUG] Query: {query}")
        print(f"[DEBUG] Params: {params}")

        cursor.execute(query, params)
        raw_results = cursor.fetchall()

        print(f"[DEBUG] Found {len(raw_results)} results")

        # Process results: replace class ID with label
        for row in raw_results:
            detection_id = row["detectionid"]
            time_generated = row["time_generated"]
            object_detected = row["object_detected"]
            confidence = row["confidence"]
            image_url = row["imageurl"]

            try:
                label = label_repo.get_label(int(object_detected))
            except (ValueError, TypeError):
                label = object_detected

            results.append((time_generated, label, confidence, image_url, detection_id))

        conn.close()

    except Exception as e:
        flash("Error loading incompliance data.", "danger")
        print(f"[ERROR] Exception: {e}")
        import traceback

        traceback.print_exc()
        return redirect(url_for("index"))

    # Total results
    total_results = len(results)
    # Compute total pages based on page size
    total_pages = max(1, math.ceil(total_results / page_size))

    # Slice results for the current page
    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size
    results_page = results[start_index:end_index]

    print(
        f"[DEBUG] Total results: {total_results}, Current page: {current_page}, Total pages: {total_pages}"
    )

    return render_template(
        "all_incompliance.html",
        results=results_page,
        lab_name=lab_name,
        camera_name=camera_name,
        cam_management=cam_management,
        user_role_management=user_role_management,
        all_labs=all_labs,
        all_cameras=all_cameras,
        all_labels=all_labels,
        selected_date=selected_date,
        selected_object_type=selected_object_type,
        current_page=current_page,
        total_pages=total_pages,
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


def get_db():
    conn = psycopg2.connect(**DB_PARAMS)
    # conn.row_factory = sqlite3.Row
    conn = psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)
    return conn


def generate_video_stream(detection_id):
    """
    Orchestrates streaming a video clip by fetching details and calling the NVR class.
    """
    # 1. Get incompliance details from the database
    details = get_incompliance_details_for_video(detection_id)

    if not details:
        print(f"No incompliance details found for ID {detection_id}")
        return

    # 2. Get NVR IP from environment and initialize the NVR object
    nvr_ip = os.getenv("NVR_IP_ADDRESS")
    if not nvr_ip:
        print("❌ NVR_IP_ADDRESS not set in .env file.")
        return

    nvr = NVR(
        nvr_ip=nvr_ip,
        fdid=None,
        username=os.getenv("NVR_USERNAME", "admin"),
        password=os.getenv("NVR_PASSWORD", "Sit12345"),
    )

    # 3. Get the naive local time directly from the database
    naive_detection_time = details["time_generated"]

    # 4. Calculate the time window using the naive local time
    start_time_local = naive_detection_time - timedelta(seconds=15)
    end_time_local = naive_detection_time + timedelta(seconds=5)

    # 5. Determine the correct MAIN stream track ID.
    channel_num = details["channel"]
    if channel_num < 100:
        track_id = (channel_num * 100) + 1
    else:
        track_id = channel_num

    # 6. Stream using the main stream track ID and LOCAL times.
    # This passes the time to the NVR without UTC conversion.
    stream_generator = nvr.stream_clip_by_time(
        start_time_local, end_time_local, track_id
    )

    frame_yielded = False
    for frame_bytes in stream_generator:
        if not frame_yielded:
            frame_yielded = True
        yield (
                b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

    if frame_yielded:
        print(f"✅ Successfully streamed using main stream track ID: {track_id}")
    else:
        print(
            f"❌ Streaming failed for track ID: {track_id}. Please check NVR settings."
        )


@app.route("/video_clip/<int:detection_id>")
@login_required
def video_clip(detection_id):
    """
    Route to stream a recorded video clip for a given incompliance.
    """
    return Response(
        generate_video_stream(detection_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/edit_camera/<int:camera_id>", methods=["GET", "POST"])
@login_required
@require_permission("camera_management")
def edit_camera(camera_id):
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    # conn.row_factory = dict_factory  # Enable dictionary-style access
    # cursor = conn.cursor()

    if request.method == "POST":
        # Handle form submission - update camera settings
        try:
            # Get form data
            name = request.form.get("name")

            # Validate and sanitize string
            try:
                name = validate_and_sanitize_text(name)
            except ValueError as e:
                flash(f"Validation error: {e}", "danger")
                return redirect(url_for("edit_camera", camera_id=camera_id))

            resolution = int(request.form.get("resolution", 1080))
            frame_rate = int(request.form.get("frame_rate", 30))
            encoding = request.form.get("encoding", "H.265")
            camera_ip_type = request.form.get("camera_ip_type", "static")
            ip_address = request.form.get("ip_address")
            subnet_mask = request.form.get("subnet_mask")
            gateway = request.form.get("gateway")
            timezone = request.form.get("timezone", "Asia/Singapore")
            channel = request.form.get("channel")
            # sync_with_ntp = 1 if request.form.get("sync_with_ntp") else 0
            sync_with_ntp = True if request.form.get("sync_with_ntp") else False
            ntp_server_address = request.form.get("ntp_server_address", "pool.ntp.org")
            manual_time = request.form.get("manual_time")

            # Use current time if manual_time is provided and NTP is disabled
            time_value = manual_time if manual_time and not sync_with_ntp else None

            # Update camera in database
            cursor.execute(
                """
                UPDATE Camera
                SET name               = %s,
                    resolution         = %s,
                    frame_rate         = %s,
                    encoding           = %s,
                    camera_ip_type     = %s,
                    ip_address         = %s,
                    subnet_mask        = %s,
                    gateway            = %s,
                    timezone           = %s,
                    sync_with_ntp      = %s,
                    ntp_server_address = %s,
                    time               = %s,
                    channel            = %s
                WHERE CameraId = %s
                """,
                (
                    name,
                    resolution,
                    frame_rate,
                    encoding,
                    camera_ip_type,
                    ip_address,
                    subnet_mask,
                    gateway,
                    timezone,
                    sync_with_ntp,
                    ntp_server_address,
                    time_value,
                    channel,
                    camera_id,
                ),
            )

            conn.commit()

            # Optionally, try to apply settings to actual camera via API
            try:
                apply_camera_settings(
                    camera_id,
                    {
                        "name": name,
                        "resolution": resolution,
                        "frame_rate": frame_rate,
                        "encoding": encoding,
                        "ip_address": ip_address,
                        "subnet_mask": subnet_mask,
                        "gateway": gateway,
                        "camera_ip_type": camera_ip_type,
                        "timezone": timezone,
                        "sync_with_ntp": sync_with_ntp,
                        "ntp_server_address": ntp_server_address,
                    },
                )
                flash("Settings applied to camera successfully!", "success")
            except Exception as e:
                flash(
                    f"Settings saved but failed to apply to camera: {str(e)}", "warning"
                )

        except Exception as e:
            conn.rollback()
            flash(f"Error updating camera settings: {str(e)}", "danger")

        finally:
            conn.close()

        return redirect(url_for("edit_camera", camera_id=camera_id))

    # GET request - fetch camera data
    cursor.execute(
        """
        SELECT c.CameraId,
               c.name,
               c.resolution,
               c.frame_rate,
               c.encoding,
               c.camera_ip_type,
               c.ip_address,
               c.subnet_mask,
               c.gateway,
               c.timezone,
               c.sync_with_ntp,
               c.ntp_server_address,
               c.time,
               c.channel,
               l.lab_name
        FROM Camera c
                 JOIN Lab l ON c.camera_lab_id = l.LabId
        WHERE c.CameraId = %s
        """,
        (camera_id,),
    )

    camera = cursor.fetchone()

    if not camera:
        flash("Camera not found", "danger")
        return redirect(url_for("index"))

    # Ensure all required fields have default values
    camera_data = {
        "CameraId": camera["cameraid"],
        "name": camera["name"] or f'Camera_{camera["cameraid"]}',
        # 'model': camera['model'] or 'Unknown',
        "resolution": camera["resolution"] or 1080,
        "frame_rate": camera["frame_rate"] or 30,
        "encoding": camera["encoding"] or "H.265",
        "camera_ip_type": camera["camera_ip_type"] or "static",
        "ip_address": camera["ip_address"] or "192.168.1.100",
        "subnet_mask": camera["subnet_mask"] or "255.255.255.0",
        "gateway": camera["gateway"] or "192.168.1.1",
        "timezone": camera["timezone"] or "Asia/Singapore",
        "sync_with_ntp": (
            camera["sync_with_ntp"] if camera["sync_with_ntp"] is not None else 0
        ),
        "ntp_server_address": camera["ntp_server_address"] or "pool.ntp.org",
        "time": camera["time"] or "",
        "lab_name": camera["lab_name"] or "Unknown Lab",
        "channel": camera["channel"] or "",
    }

    conn.close()

    cam_management = check_permission(session.get("role"), "camera_management")
    user_role_management = check_permission(session.get("role"), "user_role_management")
    return render_template(
        "edit_camera.html",
        camera=camera_data,
        cam_management=cam_management,
        user_role_management=user_role_management,
    )


@require_permission("camera_management")
def apply_device_settings(camera_ip, settings):
    """Apply device settings (name) to camera"""
    try:
        from shared.camera_discovery import CameraDiscovery

        discovery = CameraDiscovery()

        # Update device name if provided
        if "name" in settings:
            device_name = settings["name"]

            # Create new device info XML following the working pattern
            ET.register_namespace("", "http://www.hikvision.com/ver20/XMLSchema")

            # Check camera namespace first
            check_url = f"http://{camera_ip}/ISAPI/System/deviceInfo"
            check_response = requests.get(
                check_url, auth=HTTPDigestAuth(discovery.username, discovery.password)
            )

            if check_response.status_code != 200:
                raise Exception(
                    f"Failed to check device info: {check_response.status_code}"
                )

            # Determine namespace and create appropriate XML
            if "hikvision.com" in check_response.text:
                device_info = ET.Element(
                    "DeviceInfo", xmlns="http://www.hikvision.com/ver20/XMLSchema"
                )
                ET.register_namespace("", "http://www.hikvision.com/ver20/XMLSchema")
            else:
                device_info = ET.Element(
                    "DeviceInfo", xmlns="http://www.isapi.org/ver20/XMLSchema"
                )
                ET.register_namespace("", "http://www.isapi.org/ver20/XMLSchema")

            device_name_elem = ET.SubElement(device_info, "deviceName")
            device_name_elem.text = device_name

            # Convert to XML
            xml_data = ET.tostring(device_info, encoding="utf-8")

            # Send PUT request to update device name
            url = f"http://{camera_ip}/ISAPI/System/deviceInfo"
            headers = {"Content-Type": "application/xml"}

            response = requests.put(
                url,
                data=xml_data,
                headers=headers,
                auth=HTTPDigestAuth(discovery.username, discovery.password),
            )

            if response.status_code == 200:
                print(f"✅ Device name updated to '{device_name}' successfully.")
            else:
                print(
                    f"❌ Failed to update device name. Status: {response.status_code} - {response.reason}"
                )
                print("Response:", response.text)
                raise Exception(
                    f"Failed to update device name: {response.status_code} - {response.text}"
                )

    except Exception as e:
        raise Exception(f"Failed to apply device settings to {camera_ip}: {str(e)}")


@require_permission("camera_management")
def apply_camera_settings(camera_id, settings):
    """Apply all camera settings to the physical camera"""
    try:
        print("TRYING ISAPI UPDATE")
        # Get camera IP address from database
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT ip_address FROM Camera WHERE CameraId = %s", (camera_id,)
        )
        result = cursor.fetchone()
        conn.close()

        if not result:
            raise Exception(f"Camera {camera_id} not found in database")

        camera_ip = result[0]

        if not camera_ip:
            raise Exception(f"No IP address configured for camera {camera_id}")

        # Apply device settings (name)
        device_settings = {k: v for k, v in settings.items() if k in ["name"]}
        if device_settings:
            apply_device_settings(camera_ip, device_settings)

        # Apply stream settings (resolution, frame rate, encoding)
        stream_settings = {
            k: v
            for k, v in settings.items()
            if k in ["resolution", "frame_rate", "encoding"]
        }
        if stream_settings:
            apply_stream_settings(camera_ip, stream_settings)

        # Apply network settings (IP, subnet, gateway, IP type)
        network_settings = {
            k: v
            for k, v in settings.items()
            if k in ["ip_address", "subnet_mask", "gateway", "camera_ip_type"]
        }
        if network_settings:
            apply_network_settings(camera_ip, network_settings)

        # Apply time settings (timezone, NTP, NTP server)
        time_settings = {
            k: v
            for k, v in settings.items()
            if k in ["timezone", "sync_with_ntp", "ntp_server_address"]
        }
        if time_settings:
            apply_time_settings(camera_ip, time_settings)

        print(f"✅ All settings applied to camera {camera_id} at {camera_ip}")

    except Exception as e:
        raise Exception(f"Failed to apply camera settings: {str(e)}")


@require_permission("camera_management")
def apply_stream_settings(camera_ip, settings):
    """Apply stream settings to camera"""
    try:
        from shared.camera_discovery import CameraDiscovery

        discovery = CameraDiscovery()

        # Fetch current configuration
        url = f"http://{camera_ip}/ISAPI/Streaming/channels/101"
        response = requests.get(
            url, auth=HTTPDigestAuth(discovery.username, discovery.password)
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch current stream settings: {response.status_code}"
            )

        # Parse current XML
        root = ET.fromstring(response.text)

        # Determine namespace and register it to avoid prefixes
        if "hikvision.com" in response.text:
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            ET.register_namespace("", ns["hik"])
        else:
            ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
            ET.register_namespace("", ns["isapi"])

        # Update resolution if provided
        if "resolution" in settings:
            resolution = settings["resolution"]
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
                print(
                    f"🔄 Changing resolution height from {height_elem.text} to {height}"
                )
                height_elem.text = str(height)

        # Update frame rate if provided
        if "frame_rate" in settings:
            frame_rate = settings["frame_rate"]
            # Convert to camera format (25 -> 2500)
            camera_frame_rate = frame_rate * 100

            if "hikvision.com" in response.text:
                framerate_elem = root.find(".//hik:maxFrameRate", namespaces=ns)
            else:
                framerate_elem = root.find(".//isapi:maxFrameRate", namespaces=ns)

            if framerate_elem is not None:
                print(
                    f"🔄 Changing frame rate from {framerate_elem.text} to {camera_frame_rate}"
                )
                framerate_elem.text = str(camera_frame_rate)
            else:
                print("❌ maxFrameRate element not found.")

        # Update codec if provided
        if "encoding" in settings:
            codec = settings["encoding"]

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
            auth=HTTPDigestAuth(discovery.username, discovery.password),
        )

        if response.status_code == 200:
            print("✅ Stream settings updated successfully.")
        else:
            print(
                f"❌ Failed to update. Status: {response.status_code} - {response.reason}"
            )
            print("Response:", response.text)
            raise Exception(
                f"Failed to update stream settings: {response.status_code} - {response.text}"
            )

    except Exception as e:
        raise Exception(f"Failed to apply stream settings to {camera_ip}: {str(e)}")


@require_permission("camera_management")
def apply_network_settings(camera_ip, settings):
    """Apply network settings to camera"""
    try:
        from shared.camera_discovery import CameraDiscovery

        discovery = CameraDiscovery()

        # Fetch current configuration
        url = f"http://{camera_ip}/ISAPI/System/Network/interfaces/1"
        response = requests.get(
            url, auth=HTTPDigestAuth(discovery.username, discovery.password)
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch current network settings: {response.status_code}"
            )

        # Parse current XML
        root = ET.fromstring(response.text)

        # Determine namespace and register it to avoid prefixes
        if "hikvision.com" in response.text:
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            ET.register_namespace("", ns["hik"])
        else:
            ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
            ET.register_namespace("", ns["isapi"])

        # Update IP address type
        if "camera_ip_type" in settings:
            addressing_type = settings["camera_ip_type"]  # 'static' or 'dhcp'

            if "hikvision.com" in response.text:
                addressing_elem = root.find(
                    ".//hik:IPAddress/hik:addressingType", namespaces=ns
                )
            else:
                addressing_elem = root.find(
                    ".//isapi:IPAddress/isapi:addressingType", namespaces=ns
                )

            if addressing_elem is not None:
                print(
                    f"🔄 Changing IP addressing type from {addressing_elem.text} to {addressing_type}"
                )
                addressing_elem.text = addressing_type
            else:
                print("❌ addressingType element not found.")

        # Update static IP settings if provided
        if "ip_address" in settings:
            ip_address = settings["ip_address"]

            if "hikvision.com" in response.text:
                ip_elem = root.find(".//hik:IPAddress/hik:ipAddress", namespaces=ns)
            else:
                ip_elem = root.find(".//isapi:IPAddress/isapi:ipAddress", namespaces=ns)

            if ip_elem is not None:
                print(f"🔄 Changing IP address from {ip_elem.text} to {ip_address}")
                ip_elem.text = ip_address
            else:
                print("❌ ipAddress element not found.")

        if "subnet_mask" in settings:
            subnet_mask = settings["subnet_mask"]

            if "hikvision.com" in response.text:
                mask_elem = root.find(".//hik:IPAddress/hik:subnetMask", namespaces=ns)
            else:
                mask_elem = root.find(
                    ".//isapi:IPAddress/isapi:subnetMask", namespaces=ns
                )

            if mask_elem is not None:
                print(f"🔄 Changing subnet mask from {mask_elem.text} to {subnet_mask}")
                mask_elem.text = subnet_mask
            else:
                print("❌ subnetMask element not found.")

        if "gateway" in settings:
            gateway = settings["gateway"]

            if "hikvision.com" in response.text:
                gateway_elem = root.find(
                    ".//hik:IPAddress/hik:DefaultGateway/hik:ipAddress", namespaces=ns
                )
            else:
                gateway_elem = root.find(
                    ".//isapi:IPAddress/isapi:DefaultGateway/isapi:ipAddress",
                    namespaces=ns,
                )

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
            auth=HTTPDigestAuth(discovery.username, discovery.password),
        )

        if response.status_code == 200:
            print("✅ Network settings updated successfully.")
        else:
            print(
                f"❌ Failed to update network settings. Status: {response.status_code} - {response.reason}"
            )
            print("Response:", response.text)
            raise Exception(
                f"Failed to update network settings: {response.status_code} - {response.text}"
            )

    except Exception as e:
        raise Exception(f"Failed to apply network settings to {camera_ip}: {str(e)}")


@require_permission("camera_management")
def apply_time_settings(camera_ip, settings):
    """Apply time settings to camera"""
    try:
        from shared.camera_discovery import CameraDiscovery

        discovery = CameraDiscovery()

        # Update time configuration
        time_url = f"http://{camera_ip}/ISAPI/System/time"
        response = requests.get(
            time_url, auth=HTTPDigestAuth(discovery.username, discovery.password)
        )

        if response.status_code != 200:
            raise Exception(
                f"Failed to fetch current time settings: {response.status_code}"
            )

        # Parse current XML
        root = ET.fromstring(response.text)

        # Determine namespace and register it to avoid prefixes
        if "hikvision.com" in response.text:
            ns = {"hik": "http://www.hikvision.com/ver20/XMLSchema"}
            ET.register_namespace("", ns["hik"])
        else:
            ns = {"isapi": "http://www.isapi.org/ver20/XMLSchema"}
            ET.register_namespace("", ns["isapi"])

        # Update time mode based on NTP setting
        if "sync_with_ntp" in settings:
            sync_with_ntp = request.form.get("sync_with_ntp") == "1"
            time_mode = "NTP" if sync_with_ntp else "manual"

            if "hikvision.com" in response.text:
                time_mode_elem = root.find(".//hik:timeMode", namespaces=ns)
            else:
                time_mode_elem = root.find(".//isapi:timeMode", namespaces=ns)

            if time_mode_elem is not None:
                print(
                    f"🔄 Changing time mode from {time_mode_elem.text} to {time_mode}"
                )
                time_mode_elem.text = time_mode
            else:
                print("❌ timeMode element not found.")

        # Update timezone if provided
        if "timezone" in settings:
            timezone = settings["timezone"]
            # Convert timezone to camera format
            if timezone == "Asia/Singapore":
                tz_value = "CST-8:00:00"
            elif timezone == "UTC":
                tz_value = "UTC+00:00"
            else:
                tz_value = "CST-8:00:00"  # default

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
            auth=HTTPDigestAuth(discovery.username, discovery.password),
        )

        if response.status_code == 200:
            print("✅ Time settings updated successfully.")
        else:
            print(
                f"❌ Failed to update time settings. Status: {response.status_code} - {response.reason}"
            )
            print("Response:", response.text)
            raise Exception(
                f"Failed to update time settings: {response.status_code} - {response.text}"
            )

        # Update NTP server if provided
        if "ntp_server_address" in settings:
            ntp_url = f"http://{camera_ip}/ISAPI/System/time/ntpServers"
            response = requests.get(
                ntp_url, auth=HTTPDigestAuth(discovery.username, discovery.password)
            )

            if response.status_code == 200:
                ntp_root = ET.fromstring(response.text)

                # Register namespace for NTP XML
                if "hikvision.com" in response.text:
                    ET.register_namespace("", ns["hik"])
                    hostname_elem = ntp_root.find(
                        ".//hik:NTPServer/hik:hostName", namespaces=ns
                    )
                else:
                    ET.register_namespace("", ns["isapi"])
                    hostname_elem = ntp_root.find(
                        ".//isapi:NTPServer/isapi:hostName", namespaces=ns
                    )

                if hostname_elem is not None:
                    print(
                        f"🔄 Changing NTP server from {hostname_elem.text} to {settings['ntp_server_address']}"
                    )
                    hostname_elem.text = settings["ntp_server_address"]

                    # Send updated NTP XML back to camera
                    updated_ntp_xml = ET.tostring(ntp_root, encoding="utf-8")

                    response = requests.put(
                        ntp_url,
                        data=updated_ntp_xml,
                        headers=headers,
                        auth=HTTPDigestAuth(discovery.username, discovery.password),
                    )

                    if response.status_code == 200:
                        print("✅ NTP server updated successfully.")
                    else:
                        print(
                            f"❌ Failed to update NTP server. Status: {response.status_code} - {response.reason}"
                        )
                        print("Response:", response.text)
                else:
                    print("❌ NTP hostName element not found.")
            else:
                print(
                    f"❌ Failed to fetch NTP settings. Status: {response.status_code}"
                )

    except Exception as e:
        raise Exception(f"Failed to apply time settings to {camera_ip}: {str(e)}")


@app.route("/video_feed/<camera_id>")
@require_permission("video_feed")
def video_feed(camera_id):
    cam_manager = CameraManager.get_instance()

    camera_id = int(camera_id)
    if camera_id not in cam_manager.camera_pool:
        return f"Camera {camera_id} not found.", 404

    camera = cam_manager.camera_pool[camera_id]["camera"]
    print(f"[STREAM] Client connected to /video_feed/{camera_id}.")

    def generate_stream():
        while camera.running:
            try:
                frame = (camera.display_queue).get()
            except queue.Empty:
                continue

            ret, buffer = cv2.imencode(".jpg", frame)
            if not ret:
                continue

            frame = buffer.tobytes()
            yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")

    return Response(
        generate_stream(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/check_ip", methods=["POST"])
def check_ip():
    ip_address = request.json.get("ip")

    cd = CameraDiscovery()
    # Get all connected channels from the NVR
    discovered_channels = cd.get_connected_channels()
    # Pass the discovered channels to the discover_camera method
    discover_results = cd.discover_camera(ip_address, discovered_channels)
    if discover_results is None:
        return jsonify({"valid": False, "device_info": discover_results})

    return jsonify({"valid": True, "device_info": discover_results})


@app.route("/add_camera", methods=["POST"])
@login_required
@require_permission("camera_management")
def add_camera():
    try:
        data = request.get_json()
        camera_ip = data.get("ip")
        device_info = data.get("device_info")
        lab_name = data.get("lab_name")  # Get lab name from request

        print(f"🔍 Attempting to add camera: {camera_ip} to lab: {lab_name}")
        print(f"📋 Device info: {device_info}")

        if not lab_name:
            return jsonify({"success": False, "message": "Lab name is required"})

        # Check if camera already exists
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM Camera WHERE ip_address = %s", (camera_ip,)
        )
        if cursor.fetchone()[0] > 0:
            print(f"❌ Camera {camera_ip} already exists in database")
            conn.close()
            return jsonify(
                {"success": False, "message": f"Camera {camera_ip} already exists!"}
            )

        # Get the actual lab ID for the specified lab
        cursor.execute("SELECT LabId FROM Lab WHERE lab_name = %s", (lab_name,))
        lab_result = cursor.fetchone()
        if not lab_result:
            conn.close()
            return jsonify({"success": False, "message": f'Lab "{lab_name}" not found'})

        lab_id = lab_result[0]

        # Get current user ID from session
        user_id = session.get("user_id", 1)

        # Find channel ID of camera in the NVR
        from shared.camera_discovery import CameraDiscovery

        discovery = CameraDiscovery()
        all_channels = discovery.get_connected_channels()
        try:
            channel = all_channels[camera_ip]
        except Exception as e:
            return jsonify(
                {
                    "success": False,
                    "message": "No channel ID found in NVR for the camera. Check that camera is connected to NVR.",
                }
            )

        # Add to database with correct column names and all required fields
        cursor.execute(
            """
            INSERT INTO Camera (name, ip_address, camera_lab_id, camera_user_id, resolution, frame_rate,
                                encoding,
                                subnet_mask, gateway, camera_ip_type, timezone, sync_with_ntp,
                                ntp_server_address, time, channel)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING cameraid
            """,
            (
                device_info.get("device_name", f"Camera_{camera_ip}"),
                camera_ip,
                lab_id,  # Fixed: using camera_lab_id column name
                user_id,  # Added: camera_user_id is required
                device_info.get("resolution", 1080),
                device_info.get("frame_rate", 25),
                device_info.get("encoding", "H.265"),
                device_info.get("subnet_mask", "255.255.255.0"),
                device_info.get("gateway", "192.168.1.1"),
                device_info.get("camera_ip_type", "static"),
                device_info.get("timezone", "Asia/Singapore"),
                bool(device_info.get("sync_with_ntp", True)),
                device_info.get(
                    "ntp_server_address", "pool.ntp.org"
                ),  # Fixed: use correct key
                device_info.get("time", "2025-01-01T00:00:00"),
                channel,
            ),
        )

        # camera_id = cursor.lastrowid
        camera_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        print(f"✅ Camera {camera_ip} added to database with ID {camera_id}")

        # Add to camera manager
        from shared.camera_manager import CameraManager

        # Try to get existing instance first (singleton pattern)
        manager = CameraManager.get_instance()
        # except RuntimeError:
        #     # If no instance exists, create one with db_path
        #     manager = CameraManager(DATABASE)
        manager.add_new_camera(camera_id, camera_ip, True)

        print(f"✅ Camera {camera_ip} added to camera manager")

        return jsonify(
            {"success": True, "message": f"Camera {camera_ip} added successfully!"}
        )

    except Exception as e:
        print(f"❌ Error adding camera: {e}")
        return jsonify({"success": False, "message": f"Error adding camera: {str(e)}"})


@app.route("/user_management", methods=["GET", "POST"])
@login_required
@require_permission("user_role_management")
def user_management():
    role = session.get("role")
    if role is None:
        return redirect(url_for("index"))

    cam_management = check_permission(role, "camera_management")
    user_role_management = check_permission(role, "user_role_management")

    if request.method == "GET":
        dao = RoleDAO(DB_PARAMS)
        users = get_all_users()
        roles = dao.get_all_roles()

        return render_template(
            "user_management.html",
            users=users,
            roles=roles,
            cam_management=cam_management,
            user_role_management=user_role_management,
        )

    if request.method == "POST":

        user_id = request.form.get("user_id")
        action = request.form.get("action")

        conn = psycopg2.connect(**DB_PARAMS)

        if action == "delete":

            cm = CameraManager(DB_PARAMS)

            # Stop detection on cameras created by deleted user and join threads
            cursor = conn.cursor()
            cursor.execute(
                "SELECT CameraId FROM Camera WHERE camera_user_id = %s", (user_id,)
            )
            camera_id = cursor.fetchone()

            if camera_id is not None:
                success = cm.remove_camera(camera_id[0])
                if not success:
                    flash("Error stopping detection on affected cameras.", "success")
                    return redirect(url_for("user_management"))

            is_same_user = int(session.get("user_id")) == int(user_id)

            # conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()

            if is_same_user:
                return redirect(url_for("logout"))

            flash("User deleted successfully.", "success")

        elif action == "update":
            new_role = request.form.get("new_role")

            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Roles WHERE name = %s", (new_role,))
            role_exists = cursor.fetchone()
            if role_exists:
                cursor.execute(
                    "UPDATE users SET role = %s WHERE id = %s", (new_role, user_id)
                )
                conn.commit()
                flash("User role updated successfully.", "success")

        conn.close()
        return redirect(url_for("user_management"))


@app.route("/role_management", methods=["GET", "POST"])
@login_required
@require_permission("user_role_management")
def role_management():
    role = session.get("role")
    if role is None:
        return redirect(url_for("index"))

    cam_management = check_permission(role, "camera_management")
    user_role_management = check_permission(role, "user_role_management")

    dao = RoleDAO(DB_PARAMS)
    roles = dao.get_all_roles()
    permissions = dao.get_all_permissions()
    role_permissions = dao.get_all_rolepermissions()

    if request.method == "POST":
        action = request.form.get("action")

        # Add a new role
        if action == "add_role":
            new_role_name = request.form.get("role_name").lower()

            # Validate and sanitize input
            try:
                new_role_name = validate_and_sanitize_text(new_role_name)
            except ValueError as e:
                flash(f"Validation error: {e}", "danger")
                return redirect(url_for("role_management"))

            if not new_role_name:
                flash("Error creating new role.", "danger")
                return redirect(url_for("role_management"))

            success = dao.insert_new_role(new_role_name)

            if not success:
                flash("Error creating new role.", "danger")
                return redirect(url_for("role_management"))

            flash("Created new role with empty permissions.", "success")
            return redirect(url_for("role_management"))

        # Update permissions of exisitng roles
        elif action == "update":
            permissions_map = set()

            for key in request.form.keys():
                if key.startswith("role_perm_"):
                    rp = key[len("role_perm_"):]
                    role_name, perm_name = rp.split("_", 1)
                    role_id = dao.get_role_id_by_name(role_name)
                    perm_id = dao.get_permission_id_by_name(perm_name)
                    if role_id and perm_id:
                        permissions_map.add((role_id, perm_id))
            try:
                # Update role and permissions in database
                dao.update_role_permissions(permissions_map)
                flash("Permissions updated successfully.", "success")

            except Exception:
                flash("Error updating permissions.", "danger")

            return redirect(url_for("role_management"))

        elif action == "delete":
            role_name = request.form.get("role_name")
            success = dao.delete_role(role_name)

            if not success:
                flash("Error deleting role.", "danger")
                return redirect(url_for("role_management"))

            flash("Deleted role.", "success")
            return redirect(url_for("role_management"))

    return render_template(
        "role_management.html",
        roles=roles,
        permissions=permissions,
        role_permissions=role_permissions,
        cam_management=cam_management,
        user_role_management=user_role_management,
    )


@app.route("/labs", methods=["GET", "POST"])
@login_required
@require_permission("camera_management")
def labs():
    role = session.get("role")
    if role is None:
        return redirect(url_for("index"))

    cam_management = check_permission(role, "camera_management")
    user_role_management = check_permission(role, "user_role_management")

    dao = LabDAO(DB_PARAMS)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_lab":
            lab_name = request.form.get("lab_name")
            lab_safety_email = request.form.get("lab_safety_email")

            # Validate and sanitize input
            try:
                lab_name = validate_and_sanitize_text(lab_name)
                lab_safety_email = validate_and_sanitize_text(lab_safety_email)
            except ValueError as e:
                flash(f"Validation error: {e}", "danger")
                return redirect(request.url)

            success = dao.insert_lab(lab_name, lab_safety_email)

            (
                flash(f"New lab created.", "success")
                if success
                else flash(f"Error creating new lab.", "danger")
            )

        elif action == "delete":
            lab_id = request.form.get("lab_id")
            success = dao.delete_lab(lab_id)

            (
                flash(f"Lab deleted succesfully.", "success")
                if success
                else flash(f"Error deleting lab.", "danger")
            )

        elif action == "update":
            lab_id = request.form.get("lab_id")
            new_lab_name = request.form.get("new_lab_name")
            new_lab_email = request.form.get("new_lab_email")

            # Validate and sanitize string input
            try:
                new_lab_name = validate_and_sanitize_text(new_lab_name)
                new_lab_email = validate_and_sanitize_text(new_lab_email)
            except ValueError as e:
                flash(f"Validation error: {e}", "danger")
                return redirect(request.url)

            success = dao.update_lab(new_lab_name, new_lab_email, lab_id)

            (
                flash(f"Lab details updated succesfully.", "success")
                if success
                else flash(f"Failed to update lab details.", "danger")
            )

        return redirect(url_for("labs"))

    all_lab_details = dao.get_all_labs()

    return render_template(
        "labs.html",
        all_lab_details=all_lab_details,
        cam_management=cam_management,
        user_role_management=user_role_management,
    )


@app.route("/create_account", methods=["GET", "POST"])
@login_required
@require_permission("user_role_management")
def create_account():
    role = session.get("role")
    if role is None:
        return redirect(url_for("index"))

    cam_management = check_permission(role, "camera_management")
    user_role_management = check_permission(role, "user_role_management")

    dao = RoleDAO(DB_PARAMS)
    roles = dao.get_all_roles()

    if request.method == "POST":
        # Get form data
        username_form = request.form.get("username", "")
        email_form = request.form.get("email", "")
        password_form = request.form.get("password")
        role_form = request.form.get("role", "")

        # Validate and sanitize string input
        try:
            username_form = validate_and_sanitize_text(username_form)
            email_form = validate_and_sanitize_text(email_form)
            role_form = validate_and_sanitize_text(role_form)
        except ValueError as e:
            flash(f"Validation error: {e}", "danger")
            return redirect(url_for("labs"))

        # Validate required fields are not empty
        if not username_form or not email_form or not password_form or not role_form:
            flash("❌ All fields are required.", "danger")
            return render_template(
                "create_account.html",
                roles=roles,
                cam_management=cam_management,
                user_role_management=user_role_management,
            )

        # Password length validation
        if len(password_form) < 8:
            flash("❌ Password must be at least 8 characters long.", "danger")
            return render_template(
                "create_account.html",
                roles=roles,
                cam_management=cam_management,
                user_role_management=user_role_management,
            )

        # Check email uniqueness
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email_form,))
        if cursor.fetchone():
            flash("❌ An account with this email already exists.", "danger")
            return render_template(
                "create_account.html",
                roles=roles,
                cam_management=cam_management,
                user_role_management=user_role_management,
            )

        # Hash password
        password_hash = generate_password_hash(password_form)

        # Insert into DB
        try:
            # Get the ID of the role we want the new user to have
            print(f"[DEBUG] role_to_add: {role_form}")
            cursor.execute("SELECT id FROM Roles WHERE name = %s", (role_form,))
            role_to_add = cursor.fetchone()
            if not role_to_add:
                raise ValueError(f"Role '{role_form}' not found.")
            print(f"[DEBUG] role_to_add: {role_to_add}")
            role_to_add = role_to_add[0]

            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
                """,
                (username_form, email_form, password_hash, role_to_add),
            )
            conn.commit()
            flash("✅ Account created successfully!", "success")
            return redirect(url_for("user_management"))
        except psycopg2.IntegrityError:
            flash("❌ Username or email already exists.", "danger")
        except Exception as e:
            flash(f"❌ Failed to create user: {str(e)}", "danger")
        finally:
            conn.close()

    return render_template(
        "create_account.html",
        roles=roles,
        cam_management=cam_management,
        user_role_management=user_role_management,
    )


@app.route("/profile", methods=["GET"])
@login_required
def profile_redirect():
    # If user just visits /profile, redirect to /profile/basic
    return redirect("/profile/basic")


@app.route("/profile/<section>", methods=["GET", "POST"])
@login_required
def profile(section):
    # logging.debug(f"📝 WORKING!!!!")
    # logging.debug(f"📝 Session user_id: {session.get('user_id')}")
    app.logger.debug(f"📝 Profile section: {section}")
    dao = UserDAO(DB_PARAMS)

    # Get the current user from DB
    user = dao.get_user_by_id(session["user_id"])

    if section == "basic":
        if request.method == "POST":
            # Get data from the form
            email_form = request.form.get("email", "")
            username_form = request.form.get("username", "")
            password_form = request.form.get("password", "")
            cPassword_form = request.form.get("cPassword", "")

            if not username_form or not email_form:
                flash("❌ Username and email are required.", "danger")
                return redirect(url_for("profile", section="basic"))

            # Validate password match.
            if password_form and password_form != cPassword_form:
                flash("Passwords do not match!", "danger")
                return redirect(url_for("profile", section="basic"))

            try:
                # Use DAO to update the user
                rows_affected = dao.update_user(
                    session["user_id"],
                    username_form,
                    email_form,
                    password_form if password_form else None,
                )

                logging.debug(f"📝 Rows affected: {rows_affected}")

                if rows_affected > 0:
                    # Update session values if DB update succeeded
                    session["username"] = username_form
                    session["email"] = email_form
                    flash("Profile updated successfully!", "success")
                else:
                    flash("❌ No changes were made.", "warning")

            except Exception as e:
                flash(f"❌ Failed to update profile: {str(e)}", "danger")

        return render_template("profile.html", section="basic", user=user)

    elif section == "role":
        role_name = dao.get_user_role(session["user_id"])
        return render_template("profile.html", section="role", user_role=role_name)

    elif section == "permission":
        user_permissions = dao.get_user_permissions(session["user_id"])
        all_permissions = dao.get_all_permissions()
        return render_template(
            "profile.html",
            section="permission",
            user=user,
            permissions=user_permissions,
            all_permissions=all_permissions,
        )

    else:
        # If an invalid section is given → fallback to basic
        return redirect(url_for("profile", section="basic"))
    # Fetch user data for rendering (from session or DB if you want fresh values)
    session_data = dao.get_user_by_id(session["user_id"])
    return render_template("profile.html", user=session_data)


@app.route("/mqtt-test", methods=["GET"])
def mqtt_test():
    """
    Test route to publish a message to MQTT broker.
    """
    try:
        mqtt_client.publish_violation(
            user="TestUser",
            event="test_message",
            details="This is a test message from Flask.",
        )
        return jsonify({"status": "success", "message": "MQTT message sent!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
