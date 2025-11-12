import unittest
from unittest.mock import patch, MagicMock
import psycopg2

# Set environment variable for test database before importing modules that use it
import os
os.environ['POSTGRES_DB'] = os.getenv("POSTGRES_DB_TEST", "testdb")

# Now import the modules
from database import create_user, verify_user
from web.routes import app
from web.utils import login_required

# Define test routes outside the test class
@app.route('/protected')
@login_required
def protected_view():
    return "Access Granted"

class WhiteBoxTestDatabase(unittest.TestCase):
    """White-box tests for database functions, mocking the DB connection."""

    @patch('database.psycopg2.connect')
    def test_create_user_success(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (1,) 

        result = create_user("testuser", "test@example.com", "password123", "user")

        self.assertTrue(result)
        mock_cur.execute.assert_any_call("SELECT id FROM Roles WHERE name = %s", ('user',))
        mock_cur.execute.assert_any_call(
            unittest.mock.ANY,
            ('testuser', 'test@example.com', unittest.mock.ANY, 1)
        )
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('database.psycopg2.connect')
    def test_create_user_duplicate_email(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        mock_cur.execute.side_effect = [
            (1,),
            psycopg2.IntegrityError("duplicate key value violates unique constraint")
        ]

        result = create_user("testuser", "test@example.com", "password123", "user")

        self.assertFalse(result)
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('database.psycopg2.connect')
    @patch('database.check_password_hash')
    def test_verify_user_valid_credentials(self, mock_check_password, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        mock_user_data = {'id': 1, 'email': 'test@example.com', 'username': 'testuser', 'password_hash': 'hashed_pass', 'role': 'user'}
        mock_cur.fetchone.return_value = mock_user_data
        mock_check_password.return_value = True

        user = verify_user('test@example.com', 'password123')

        self.assertIsNotNone(user)
        self.assertEqual(user['email'], 'test@example.com')
        mock_check_password.assert_called_with('hashed_pass', 'password123')

    @patch('database.psycopg2.connect')
    @patch('database.check_password_hash')
    def test_verify_user_invalid_credentials(self, mock_check_password, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        mock_user_data = {'id': 1, 'email': 'test@example.com', 'username': 'testuser', 'password_hash': 'hashed_pass', 'role': 'user'}
        mock_cur.fetchone.return_value = mock_user_data
        mock_check_password.return_value = False

        user = verify_user('test@example.com', 'wrongpassword')

        self.assertIsNone(user)
        mock_check_password.assert_called_with('hashed_pass', 'wrongpassword')

class WhiteBoxTestFlaskApp(unittest.TestCase):
    """White-box tests for the Flask application logic."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    @patch('web.routes.inject_labs_with_cameras', return_value={})
    def test_login_required_decorator_redirect(self, mock_inject_labs):
        """Test login_required decorator redirects when not logged in."""
        response = self.client.get('/protected', follow_redirects=True)
        
        self.assertIn(b'Please log in to access this page', response.data)
        self.assertEqual(response.status_code, 200)
        mock_inject_labs.assert_called()

    def test_login_required_decorator_allows_access(self):
        """Test login_required decorator allows access when logged in."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess['user_id'] = 1
                sess['username'] = 'test'
                sess['role'] = 'user'
            
            response = c.get('/protected')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Access Granted', response.data)

if __name__ == '__main__':
    unittest.main()