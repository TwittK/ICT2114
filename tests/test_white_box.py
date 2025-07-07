import unittest
import sqlite3
import os
import sys
from unittest.mock import patch, MagicMock, mock_open
from werkzeug.security import generate_password_hash
from datetime import datetime

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules
try:
    from database import (create_user, verify_user, create_lab, create_camera, 
                         init_database, create_default_admin, update_last_login,
                         create_default_labs_and_cameras)
    from app import app
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure your database.py and app.py files are in the correct location")

class WhiteBoxTestDatabase(unittest.TestCase):
    def setUp(self):
        """Set up test database"""
        self.test_db = 'test_white_box.sqlite'
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        # Mock the init_db.sql file content
        self.mock_sql_content = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        );
        
        CREATE TABLE IF NOT EXISTS Lab (
            LabId INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_name TEXT UNIQUE NOT NULL,
            lab_safety_email TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS Camera (
            CameraId INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            resolution INTEGER NOT NULL,
            frame_rate INTEGER NOT NULL,
            encoding VARCHAR(50) NOT NULL,
            camera_ip_type VARCHAR(50) DEFAULT 'static' CHECK (camera_ip_type IN ('static', 'dhcp')),
            ip_address VARCHAR(50) NOT NULL,
            subnet_mask VARCHAR(50) NOT NULL,
            gateway VARCHAR(50) NOT NULL,
            timezone VARCHAR(100) NOT NULL,
            sync_with_ntp INTEGER NOT NULL DEFAULT 0,
            ntp_server_address VARCHAR(100) DEFAULT NULL,
            time DATETIME NOT NULL,
            camera_user_id INTEGER NOT NULL,
            camera_lab_id INTEGER NOT NULL,
            FOREIGN KEY (camera_user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (camera_lab_id) REFERENCES Lab (LabId) ON DELETE CASCADE
        );
        """
    
    def tearDown(self):
        """Clean up test database"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_create_user_success(self):
        """Test successful user creation"""
        with patch('database.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            result = create_user("testuser", "test@test.com", "password123")
            
            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()
            self.assertTrue(result)

    def test_create_user_duplicate_email(self):
        """Test user creation with duplicate email"""
        with patch('database.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.execute.side_effect = sqlite3.IntegrityError("UNIQUE constraint failed")
            
            result = create_user("testuser", "test@test.com", "password123")
            
            self.assertFalse(result)

    def test_verify_user_valid_credentials(self):
        """Test user verification with valid credentials"""
        with patch('database.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            password_hash = generate_password_hash("password123")
            mock_cursor.fetchone.return_value = (1, "test@test.com", "testuser", password_hash, "user", 1)
            
            result = verify_user("test@test.com", "password123")
            self.assertIsNotNone(result)
            self.assertEqual(result['username'], "testuser")

    def test_verify_user_invalid_credentials(self):
        """Test user verification with invalid credentials"""
        with patch('database.sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None
            
            result = verify_user("nonexistent@test.com", "password123")
            self.assertIsNone(result)

class WhiteBoxTestFlaskApp(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_login_required_decorator_redirect(self):
        """Test login_required decorator redirects when not logged in"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)

    def test_login_required_decorator_allows_access(self):
        """Test login_required decorator allows access when logged in"""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['role'] = 'admin'
        
        with patch('app.sqlite3.connect'):
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()