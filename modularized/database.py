import os, time
from dotenv import load_dotenv
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables from .env
load_dotenv()
DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}


def init_database(retries=5, delay=3):
    print("Connecting to DB with params:", DB_PARAMS)

    attempt = 0
    conn = None
    while attempt < retries:
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            print("✅ Database connection established.")
            break
        except psycopg2.OperationalError as e:
            attempt += 1
            print(f"❌ DB not ready (attempt {attempt}/{retries}): {e}")
            time.sleep(delay)
    else:
        raise Exception("🚨 Could not connect to the database after multiple retries.")

    cursor = conn.cursor()

    try:
        # Read and execute SQL schema
        with open("init_db.sql", "r") as f:
            sql_script = f.read()

        cursor.execute(sql_script)
        conn.commit()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print("🚨 Error while initializing the database:", e)
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


# def init_database():
#     # Connect to PostgreSQL
#     conn = psycopg2.connect(**DB_PARAMS)

#     cursor = conn.cursor()

#     # Read SQL schema
#     with open("init_db.sql", "r") as f:
#         sql_script = f.read()

#     # Execute schema
#     cursor.execute(sql_script)

#     conn.commit()
#     cursor.close()
#     conn.close()


def insert_default_roles():
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    try:
        cursor.execute("""INSERT INTO Roles (name) VALUES ('admin'), ('user');""")

        cursor.execute(
            """            
            INSERT INTO Permission (name) VALUES
            ('camera_management'),
            ('view_incompliances'),
            ('video_feed'),
            ('user_role_management')
        """
        )

        cursor.execute(
            "INSERT INTO RolePermission (role_id, permission_id) SELECT 1, id FROM Permission;"
        )
        cursor.execute(
            "INSERT INTO RolePermission (role_id, permission_id) SELECT 2, id FROM Permission WHERE name IN ('view_incompliances', 'video_feed');"
        )

        conn.commit()

        return True
    except psycopg2.IntegrityError:

        return False
    finally:
        conn.close()


def create_default_admin():
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT COUNT(*)
    FROM users u
    JOIN roles r ON u.role = r.id
    WHERE r.name = %s
    """,
        ("admin",),
    )
    admin_count = cursor.fetchone()[0]

    cursor.execute(
        """
    SELECT COUNT(*)
    FROM users u
    JOIN roles r ON u.role = r.id
    WHERE r.name = %s
    """,
        ("user",),
    )
    user_count = cursor.fetchone()[0]

    conn.close()

    if admin_count == 0:
        create_user("admin", "admin@labcomply.com", "admin123", "admin")
        print("Default admin user created: admin/admin123")

    if user_count == 0:
        create_user("user", "user@labcomply.com", "user123", "user")
        print("Default user account created: user/user123")


def create_user(username, email, password, role_name="user"):
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    password_hash = generate_password_hash(password)

    try:
        # Look up role id by name
        cursor.execute("SELECT id FROM Roles WHERE name = %s", (role_name,))
        role_id = cursor.fetchone()
        if not role_id:
            raise ValueError(f"Role '{role_name}' does not exist")

        role_id = role_id[0]

        # Insert user
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
        """,
            (username, email, password_hash, role_id),
        )

        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def create_default_labs_and_cameras():
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    cursor.execute(
        """
                   SELECT COUNT(*)
                   FROM Lab
                   """
    )
    lab_count = cursor.fetchone()[0]

    cursor.execute(
        """
                   SELECT COUNT(*)
                   FROM Camera
                   """
    )
    camera_count = cursor.fetchone()[0]

    conn.close()

    if lab_count == 0:
        create_lab_and_email("E2-L6-016", "labsafety@gmail.com")
        # create_lab("E2-L6-017", "labsafety@Fgmail.com")

    if camera_count == 0:
        create_camera("Camera 1", 1, 1, ip_address="192.168.1.64")
        # create_camera("Camera 2", 1, 1, ip_address="192.168.1.65")


def create_lab_and_email(lab_name, lab_safety_email):
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
                       INSERT INTO Lab (lab_name)
                       VALUES (%s)
                       RETURNING LabId
                       """,
            (lab_name,),
        )

        lab_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO LabSafetyStaff (lab_safety_email, lab_id)
            VALUES (%s, %s)
            """,
            (lab_safety_email, lab_id)
        )

        conn.commit()
        return True
    except psycopg2.IntegrityError:
        return False
    finally:
        conn.close()


def create_camera(
    name,
    camera_user_id,
    camera_lab_id,
    resolution=1080,
    frame_rate=30,
    encoding="H.265",
    camera_ip_type="static",
    ip_address="192.168.1.100",
    subnet_mask="255.255.255.0",
    gateway="192.168.1.1",
    timezone="Asia/Singapore",
    sync_with_ntp=False,
    ntp_server_address="pool.ntp.org",
    time="2025-01-01T00:00:00",
):
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
                       INSERT INTO Camera (name, resolution, frame_rate,
                                           encoding, camera_ip_type, ip_address,
                                           subnet_mask, gateway, timezone,
                                           sync_with_ntp, ntp_server_address, time,
                                           camera_user_id, camera_lab_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                time,
                camera_user_id,
                camera_lab_id,
            ),
        )

        conn.commit()
        return True
    except psycopg2.IntegrityError:
        return False
    finally:
        conn.close()


def get_lab_safety_email_by_camera_id(camera_id):
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT Lab.lab_safety_email
        FROM Camera
        JOIN Lab ON Camera.camera_lab_id = Lab.LabId
        WHERE Camera.ROWID = %s
    """,
        (camera_id,),
    )

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None


def create_new_camera(
    name,
    camera_user_id,
    camera_lab_id,
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
    time,
):
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
                       INSERT INTO Camera (name, resolution, frame_rate,
                                           encoding, camera_ip_type, ip_address,
                                           subnet_mask, gateway, timezone,
                                           sync_with_ntp, ntp_server_address, time,
                                           camera_user_id, camera_lab_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING camera_id;
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
                time,
                camera_user_id,
                camera_lab_id,
            ),
        )

        camera_id = cursor.fetchone()[0]  # Fetch the camera_id returned by the query
        conn.commit()
        return True, camera_id
    except psycopg2.IntegrityError:
        return False, None
    finally:
        conn.close()


def verify_user(email, password):

    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT u.id, u.email, u.username, u.password_hash,
               r.name AS role_name, u.is_active
        FROM users u
        JOIN Roles r ON u.role = r.id
        WHERE u.email = %s
          AND u.is_active = TRUE
    """,
        (email,),
    )

    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[3], password):
        return {
            "id": user[0],
            "email": user[1],
            "username": user[2],
            "role": user[4],
        }

    return None


def update_last_login(user_id):

    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    cursor.execute(
        """
                   UPDATE users
                   SET last_login = CURRENT_TIMESTAMP
                   WHERE id = %s
                   """,
        (user_id,),
    )

    conn.commit()
    cursor.close()
    conn.close()


def get_all_users():
    # Connect to PostgreSQL
    conn = psycopg2.connect(**DB_PARAMS)

    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users")
    columns = [desc[0] for desc in cursor.description]  # Extract column names
    users = cursor.fetchall()

    conn.close()

    # return [dict(row) for row in users]
    # Convert rows to dictionaries
    return [dict(zip(columns, row)) for row in users]


if __name__ == "__main__":
    init_database()
    insert_default_roles()
    create_default_admin()
    # Mock lab and cameras
    create_default_labs_and_cameras()
