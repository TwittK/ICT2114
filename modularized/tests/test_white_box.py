import unittest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

# Set environment variable for test database before importing modules that use it
import os
os.environ['POSTGRES_DB'] = os.getenv("POSTGRES_DB_TEST", "testdb")

# Now import the modules
from modularized.database import create_user, verify_user
from modularized.web.routes import app
from modularized.web.utils import login_required

class WhiteBoxTestDatabase(unittest.TestCase):
    """White-box tests for database functions, mocking the DB connection."""

    @patch('modularized.database.psycopg2.connect')
    def test_create_user_success(self, mock_connect):
        """Test successful user creation by mocking the database connection."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Simulate role ID lookup
        mock_cur.fetchone.return_value = (1,) 

        result = create_user("testuser", "test@example.com", "password123", "user")

        self.assertTrue(result)
        mock_cur.execute.assert_any_call("SELECT id FROM Roles WHERE name = %s", ('user',))
        mock_cur.execute.assert_any_call(
            unittest.mock.ANY, # SQL string
            ('testuser', 'test@example.com', unittest.mock.ANY, 1) # Params
        )
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('modularized.database.psycopg2.connect')
    def test_create_user_duplicate_email(self, mock_connect):
        """Test user creation with duplicate email by simulating an IntegrityError."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        
        # Simulate role ID lookup
        mock_cur.fetchone.return_value = (1,)
        # Simulate a database integrity error (e.g., unique constraint violation)
        mock_cur.execute.side_effect = [None, psycopg2.IntegrityError]

        result = create_user("testuser", "test@example.com", "password123", "user")

        self.assertFalse(result)
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('modularized.database.psycopg2.connect')
    @patch('modularized.database.check_password_hash')
    def test_verify_user_valid_credentials(self, mock_check_password, mock_connect):
        """Test user verification with valid credentials."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Mock return value for the user query
        mock_user_data = (1, 'test@example.com', 'testuser', 'hashed_pass', 'user', True)
        mock_cur.fetchone.return_value = mock_user_data
        # Mock password check to return True
        mock_check_password.return_value = True

        user = verify_user('test@example.com', 'password123')

        self.assertIsNotNone(user)
        self.assertEqual(user['email'], 'test@example.com')
        mock_check_password.assert_called_with('hashed_pass', 'password123')
        mock_conn.close.assert_called_once()

    @patch('modularized.database.psycopg2.connect')
    @patch('modularized.database.check_password_hash')
    def test_verify_user_invalid_credentials(self, mock_check_password, mock_connect):
        """Test user verification with invalid credentials."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        mock_user_data = (1, 'test@example.com', 'testuser', 'hashed_pass', 'user', True)
        mock_cur.fetchone.return_value = mock_user_data
        # Mock password check to return False
        mock_check_password.return_value = False

        user = verify_user('test@example.com', 'wrongpassword')

        self.assertIsNone(user)
        mock_check_password.assert_called_with('hashed_pass', 'wrongpassword')
        mock_conn.close.assert_called_once()

class WhiteBoxTestFlaskApp(unittest.TestCase):
    """White-box tests for the Flask application logic."""

    def setUp(self):
        """Set up a test client for the Flask app."""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = app.test_client()

    def test_login_required_decorator_redirect(self):
        """Test login_required decorator redirects when not logged in."""
        # A dummy route protected by the decorator
        @app.route('/protected')
        @login_required
        def protected_view():
            return "You should not see this"

        response = self.client.get('/protected', follow_redirects=True)
        self.assertIn(b'Please log in to access this page', response.data)
        self.assertEqual(response.status_code, 200) # After redirect

    def test_login_required_decorator_allows_access(self):
        """Test login_required decorator allows access when logged in."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess['user'] = {'id': 1, 'username': 'test', 'role': 'user'}
            
            # Dummy route
            @app.route('/protected_access')
            @login_required
            def protected_view_access():
                return "Access Granted"

            response = c.get('/protected_access')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Access Granted', response.data)

if __name__ == '__main__':
    unittest.main()