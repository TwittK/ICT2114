import unittest
import psycopg2
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Load environment variables from the correct path
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'modularized', '.env'))

# Database connection parameters for the test database
DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB_TEST", "testdb"), # Fallback to a default test DB name
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT"),
}

# Ensure the main app's database module uses the test DB for these tests
# This is a common practice in testing to isolate test runs.
os.environ['POSTGRES_DB'] = DB_PARAMS['dbname']
from modularized.database import (
    verify_user, 
    create_user, 
    get_all_users, 
    create_lab, 
    create_camera,
    get_lab_safety_email_by_camera_id,
    get_lab_safety_telegram_by_camera_id
)

class TestBlackBox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up a test database and populate it with initial data."""
        try:
            cls.conn = psycopg2.connect(**DB_PARAMS)
            cls.cur = cls.conn.cursor()
        except psycopg2.OperationalError as e:
            raise unittest.SkipTest(f"Could not connect to test database: {e}")

        # Clean up any previous test runs
        cls.cur.execute("DROP TABLE IF EXISTS Snapshot, Person, Camera, LabSafetyStaff, Lab, users, RolePermission, Permission, Roles CASCADE;")
        cls.conn.commit()

        # Re-create tables from the schema file
        schema_path = os.path.join(os.path.dirname(__file__), '..', 'modularized', 'init_db.sql')
        with open(schema_path, 'r') as f:
            cls.cur.execute(f.read())
        cls.conn.commit()

        # Insert foundational data (roles and permissions)
        cls.cur.execute("INSERT INTO Roles (name) VALUES ('admin'), ('user') ON CONFLICT (name) DO NOTHING;")
        cls.cur.execute("""
            INSERT INTO Permission (name) VALUES
            ('camera_management'), ('view_incompliances'), ('video_feed'), ('user_role_management')
            ON CONFLICT (name) DO NOTHING;
        """)
        cls.conn.commit()

        # Create a default user for foreign key constraints
        hashed_password = generate_password_hash("defaultpass")
        cls.cur.execute("SELECT id FROM Roles WHERE name = 'admin'")
        role_id = cls.cur.fetchone()[0]
        cls.cur.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s) RETURNING id",
            ("default_user", "default@user.com", hashed_password, role_id)
        )
        cls.default_user_id = cls.cur.fetchone()[0]
        cls.conn.commit()


    @classmethod
    def tearDownClass(cls):
        """Clean up the test database by dropping all tables."""
        if hasattr(cls, 'cur'):
            cls.cur.execute("DROP TABLE IF EXISTS Snapshot, Person, Camera, LabSafetyStaff, Lab, users, RolePermission, Permission, Roles CASCADE;")
            cls.conn.commit()
            cls.cur.close()
        if hasattr(cls, 'conn'):
            cls.conn.close()

    def setUp(self):
        """Clean user table before each test to ensure isolation."""
        self.cur.execute("DELETE FROM LabSafetyStaff;")
        self.cur.execute("DELETE FROM Camera;")
        self.cur.execute("DELETE FROM Lab;")
        self.cur.execute("DELETE FROM users WHERE id != %s;", (self.default_user_id,))
        self.conn.commit()

    def test_user_creation(self):
        """Test if a new user can be created successfully."""
        success = create_user("testuser1", "test1@example.com", "password123", "user")
        self.assertTrue(success, "User creation should return True on success.")

        # Verify the user exists in the database
        self.cur.execute("SELECT username FROM users WHERE email = 'test1@example.com'")
        user = self.cur.fetchone()
        self.assertIsNotNone(user)
        self.assertEqual(user[0], "testuser1")

    def test_lab_and_camera_creation(self):
        """Test if a lab and a camera can be created successfully."""
        # Create a lab first
        lab_id = create_lab("Test Lab E1-01")
        self.assertIsNotNone(lab_id, "create_lab should return the new lab's ID.")

        # Verify lab exists
        self.cur.execute("SELECT lab_name FROM Lab WHERE LabId = %s", (lab_id,))
        lab = self.cur.fetchone()
        self.assertEqual(lab[0], "Test Lab E1-01")

        # Create a camera linked to the lab and default user
        camera_id = create_camera(
            name="TestCam-01",
            camera_user_id=self.default_user_id,
            camera_lab_id=lab_id,
            channel=101,
            ip_address="192.168.1.101"
        )
        self.assertIsNotNone(camera_id, "create_camera should return the new camera's ID.")

        # Verify camera exists
        self.cur.execute("SELECT name, camera_lab_id FROM Camera WHERE CameraId = %s", (camera_id,))
        camera = self.cur.fetchone()
        self.assertEqual(camera[0], "TestCam-01")
        self.assertEqual(camera[1], lab_id)

    def test_get_lab_safety_contact_info(self):
        """Test retrieving lab safety staff contact details by camera ID."""
        # Setup: Create Lab, Camera, and LabSafetyStaff
        lab_id = create_lab("Safety Test Lab")
        camera_id = create_camera("SafetyCam", self.default_user_id, lab_id, 101, "192.168.1.102")
        
        safety_email = "safety.officer@test.com"
        safety_telegram = "safety_officer_tg"
        self.cur.execute(
            "INSERT INTO LabSafetyStaff (lab_safety_email, lab_safety_telegram, lab_id) VALUES (%s, %s, %s)",
            (safety_email, safety_telegram, lab_id)
        )
        self.conn.commit()

        # Test email retrieval
        retrieved_email = get_lab_safety_email_by_camera_id(camera_id)
        self.assertEqual(retrieved_email, safety_email)

        # Test telegram retrieval
        retrieved_telegram = get_lab_safety_telegram_by_camera_id(camera_id)
        self.assertEqual(retrieved_telegram, safety_telegram)

    def test_user_login_success(self):
        """Test case for a successful user login."""
        password = "password123"
        create_user("logintest", "login@test.com", password, "user")

        # The function to be tested (black-box approach)
        user = verify_user("login@test.com", password)

        self.assertIsNotNone(user, "verify_user should return a user dictionary on success.")
        self.assertEqual(user['email'], "login@test.com")
        self.assertEqual(user['role'], "user")

    def test_user_login_failure_wrong_password(self):
        """Test case for a login attempt with a wrong password."""
        password = "password123"
        create_user("loginfail", "fail@test.com", password, "user")

        user = verify_user("fail@test.com", "wrongpassword")

        self.assertIsNone(user, "verify_user should return None for a wrong password.")

    def test_user_login_failure_nonexistent_user(self):
        """Test case for a login attempt with a non-existent email."""
        user = verify_user("nonexistent@test.com", "anypassword")
        self.assertIsNone(user, "verify_user should return None for a non-existent user.")

    def test_get_all_users(self):
        """Test retrieving all users from the database."""
        create_user("userA", "a@test.com", "passA", "user")
        create_user("userB", "b@test.com", "passB", "admin")

        users = get_all_users()

        self.assertEqual(len(users), 2, "Should retrieve all created users.")
        usernames = {u['username'] for u in users}
        self.assertIn("userA", usernames)
        self.assertIn("userB", usernames)

if __name__ == '__main__':
    unittest.main()