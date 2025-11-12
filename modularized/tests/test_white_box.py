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

class WhiteBoxTestFlaskApp(unittest.TestCase):
    """White-box tests for the Flask application logic."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    @patch('psycopg2.connect')
    def test_login_required_decorator_redirect(self, mock_connect):
        """Test login_required decorator redirects when not logged in."""
        # Mock the database connection for the context processor
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = []  # Return empty labs/cameras
        
        # Don't follow redirects so we can check the redirect happened
        response = self.client.get('/protected', follow_redirects=False)
        
        # Check that we got a redirect response
        self.assertEqual(response.status_code, 302)
        # Check that the redirect is to the login page
        self.assertIn('/login', response.location)

    @patch('psycopg2.connect')
    def test_login_required_decorator_allows_access(self, mock_connect):
        """Test login_required decorator allows access when logged in."""
        # Mock the database connection for the context processor
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = []  # Return empty labs/cameras
        
        with self.client.session_transaction() as sess:
            # FIX: Set 'logged_in' which is what the decorator actually checks for
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['username'] = 'test'
            sess['role'] = 'user'
        
        response = self.client.get('/protected')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Access Granted', response.data)

if __name__ == '__main__':
    unittest.main()