import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite_vec


def init_database():
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    sqlite_version, vec_version = conn.execute("select sqlite_version(), vec_version()").fetchone()
    print(f"sqlite_version={sqlite_version}, vec_version={vec_version}")

    # Read and execute the SQL file
    with open('init_db.sql', 'r') as sql_file:
        sql_script = sql_file.read()
        cursor.executescript(sql_script)

    conn.commit()
    conn.close()


def create_user(username, email, password, role='user'):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    password_hash = generate_password_hash(password)

    try:
        cursor.execute('''
                       INSERT INTO users (username, email, password_hash, role)
                       VALUES (?, ?, ?, ?)
                       ''', (username, email, password_hash, role))

        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(email, password):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT id, email, username, password_hash, role, is_active
                   FROM users
                   WHERE email = ?
                     AND is_active = 1
                   ''', (email,))

    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[3], password):
        return {
            'id': user[0],
            'email': user[1],
            'username': user[2],
            'role': user[4],
        }
    return None


def update_last_login(user_id):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
                   UPDATE users
                   SET last_login = CURRENT_TIMESTAMP
                   WHERE id = ?
                   ''', (user_id,))

    conn.commit()
    conn.close()


def create_default_admin():
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
    admin_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "user"')
    user_count = cursor.fetchone()[0]

    conn.close()

    if admin_count == 0:
        create_user('admin', 'admin@labcomply.com', 'admin123', 'admin')
        print("Default admin user created: admin/admin123")

    if user_count == 0:
        create_user('user', 'user@labcomply.com', 'user123', 'user')
        print("Default user account created: user/user123")


def create_default_labs_and_cameras():
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute("""
                   SELECT COUNT(*)
                   FROM Lab
                   """)
    lab_count = cursor.fetchone()[0]

    cursor.execute("""
                   SELECT COUNT(*)
                   FROM Camera
                   """)
    camera_count = cursor.fetchone()[0]

    conn.close()

    if lab_count == 0:
        create_lab("E2-L6-016", "labsafety@gmail.com")
        create_lab("E2-L6-017", "labsafety@gmail.com")

    if camera_count == 0:
        create_camera("Camera 1", 1, 1)
        create_camera("Camera 2", 1, 1)

        create_camera("Camera 1", 1, 2)
        create_camera("Camera 2", 1, 2)


def create_lab(lab_name, lab_safety_email):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       INSERT INTO Lab (lab_name, lab_safety_email)
                       VALUES (?, ?)
                       ''', (lab_name, lab_safety_email))

        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def create_camera(
        name,
        camera_user_id,
        camera_lab_id,
        resolution=1080,
        frame_rate=30,
        encoding='H.265',
        camera_ip_type='static',
        ip_address='192.168.1.100',
        subnet_mask='255.255.255.0',
        gateway='192.168.1.1',
        timezone='Asia/Singapore',
        sync_with_ntp=0,
        ntp_server_address='pool.ntp.org',
        time='2025-01-01T00:00:00',

):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       INSERT INTO Camera (name, resolution, frame_rate,
                                           encoding, camera_ip_type, ip_address,
                                           subnet_mask, gateway, timezone,
                                           sync_with_ntp, ntp_server_address, time,
                                           camera_user_id, camera_lab_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (name, resolution, frame_rate,
                             encoding, camera_ip_type, ip_address,
                             subnet_mask, gateway, timezone,
                             sync_with_ntp, ntp_server_address, time,
                             camera_user_id, camera_lab_id)
                       )

        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()