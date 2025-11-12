import unittest
import os
from unittest.mock import patch, MagicMock, call
from werkzeug.security import generate_password_hash

# Set environment variable for test database before importing modules that use it
os.environ['POSTGRES_DB'] = os.getenv("POSTGRES_DB_TEST", "testdb")

from web.utils import check_permission, validate_and_sanitize_text
from database import create_user
from threads.notificationservice import NotificationService
from shared.detection_manager import DetectionManager

class TestWhiteBox(unittest.TestCase):

    @patch('web.utils.psycopg2.connect')
    def test_check_permission_granted(self, mock_connect):
        """Test the check_permission function when permission is granted."""
        # Mock the database connection and cursor
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate that the query finds a matching permission
        mock_cur.fetchone.return_value = (1,)

        # Call the function
        role_name = 'admin'
        action = 'camera_management'
        result = check_permission(role_name, action)

        # Assertions
        self.assertTrue(result)
        mock_cur.execute.assert_called_once()
        # Check if the SQL query is constructed as expected
        self.assertIn("WHERE r.name = %s AND p.name = %s", mock_cur.execute.call_args[0][0])
        self.assertEqual(mock_cur.execute.call_args[0][1], (role_name, action))
        mock_conn.close.assert_called_once()

    @patch('web.utils.psycopg2.connect')
    def test_check_permission_denied(self, mock_connect):
        """Test the check_permission function when permission is denied."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate that the query finds no matching permission
        mock_cur.fetchone.return_value = None

        result = check_permission('user', 'camera_management')

        self.assertFalse(result)
        mock_cur.execute.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_validate_and_sanitize_text_valid(self):
        """Test validate_and_sanitize_text with valid input."""
        text = "  Valid Text 123!  "
        sanitized = validate_and_sanitize_text(text)
        self.assertEqual(sanitized, "Valid Text 123!")

    def test_validate_and_sanitize_text_with_html(self):
        """Test that HTML tags are stripped."""
        text = "<p>Hello <b>World</b></p>"
        sanitized = validate_and_sanitize_text(text)
        self.assertEqual(sanitized, "Hello World")

    def test_validate_and_sanitize_text_too_long(self):
        """Test input that is too long."""
        text = "a" * 101
        with self.assertRaises(ValueError) as context:
            validate_and_sanitize_text(text)
        self.assertIn("length must be between 1 and 100", str(context.exception))

    def test_validate_and_sanitize_text_empty(self):
        """Test empty input after stripping whitespace."""
        text = "   "
        with self.assertRaises(ValueError):
            validate_and_sanitize_text(text)

    def test_validate_and_sanitize_text_not_string(self):
        """Test non-string input."""
        with self.assertRaises(ValueError) as context:
            validate_and_sanitize_text(12345)
        self.assertIn("Input must be a string", str(context.exception))

    @patch('threads.notificationservice.smtplib.SMTP')
    def test_notification_send_email(self, mock_smtp):
        """Test the internal logic of sending an email."""
        # Setup mock SMTP server
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        # Call the function
        service = NotificationService()
        to_email = "recipient@example.com"
        subject = "Test Subject"
        body = "Test Body"
        service.send_email(to_email, subject, body)

        # Assertions
        mock_smtp.assert_called_with(service.gmail_smtp_host, service.gmail_smtp_port)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_with(service.sender_email, service.sender_password)
        mock_server.sendmail.assert_called_once()
        # Check that the correct sender and recipient are used
        self.assertEqual(mock_server.sendmail.call_args[0][0], service.sender_email)
        self.assertEqual(mock_server.sendmail.call_args[0][1], to_email)
        # Check that subject is in the email content
        self.assertIn(f"Subject: {subject}", mock_server.sendmail.call_args[0][2])

    @patch('threads.notificationservice.requests.post')
    def test_notification_send_telegram(self, mock_post):
        """Test the internal logic of sending a Telegram message."""
        mock_post.return_value.status_code = 200

        service = NotificationService()
        service.send_telegram('123456789', 'Hello Telegram')

        expected_url = f'https://api.telegram.org/bot{service.bot_token}/sendMessage'
        expected_payload = {
            'chat_id': '123456789',
            'text': 'Hello Telegram',
            'parse_mode': 'Markdown'
        }

        # FIX: Change json= to data= to match the actual implementation
        mock_post.assert_called_once_with(expected_url, data=expected_payload)

    @patch('shared.detection_manager.DetectionWorker')
    def test_detection_manager_round_robin(self, MockWorker):
        """Test that the DetectionManager distributes work in a round-robin fashion."""
        num_workers = 3
        manager = DetectionManager(num_workers=num_workers)

        # Verify the manager created the correct number of workers
        self.assertEqual(len(manager.workers), num_workers)

        # Submit multiple frames to test round-robin
        manager.submit_frame('frame1', 'cam1')
        manager.submit_frame('frame2', 'cam2')
        manager.submit_frame('frame3', 'cam3')
        manager.submit_frame('frame4', 'cam4')  # This should wrap back to worker 0

        # Verify each worker received work in round-robin order
        # Worker 0 should receive frames 1 and 4
        manager.workers[0].submit.assert_any_call('frame1', 'cam1')
        manager.workers[0].submit.assert_any_call('frame4', 'cam4')
        self.assertEqual(manager.workers[0].submit.call_count, 2)

        # Worker 1 should receive frame 2
        manager.workers[1].submit.assert_called_once_with('frame2', 'cam2')

        # Worker 2 should receive frame 3
        manager.workers[2].submit.assert_called_once_with('frame3', 'cam3')

        # Verify the index wraps around correctly
        self.assertEqual(manager.current_worker_index, 1)  # Should be at position 1 after 4 submissions


    @patch('database.psycopg2.connect')
    def test_create_user_role_not_found(self, mock_connect):
        """Test create_user when the specified role does not exist."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate that the role lookup returns no result
        mock_cur.fetchone.return_value = None

        with self.assertRaises(ValueError) as context:
            create_user("test", "test@test.com", "pass", "nonexistent_role")

        self.assertIn("Role 'nonexistent_role' does not exist", str(context.exception))
        # Ensure no user insertion was attempted
        self.assertEqual(mock_cur.execute.call_count, 1) # Only the SELECT for role
        mock_conn.rollback.assert_not_called() # No transaction to rollback
        mock_conn.close.assert_called_once()

if __name__ == '__main__':
    unittest.main()