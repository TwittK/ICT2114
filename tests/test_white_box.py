import unittest
import os
from unittest.mock import patch, MagicMock, call
from werkzeug.security import generate_password_hash

# Set environment variable for test database before importing modules that use it
os.environ['POSTGRES_DB'] = os.getenv("POSTGRES_DB_TEST", "testdb")

from modularized.web.utils import check_permission, validate_and_sanitize_text
from modularized.database import create_user
from modularized.threads.notificationservice import NotificationService
from modularized.shared.detection_manager import DetectionManager

class TestWhiteBox(unittest.TestCase):

    @patch('modularized.web.utils.psycopg2.connect')
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

    @patch('modularized.web.utils.psycopg2.connect')
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

    @patch('modularized.threads.notificationservice.smtplib.SMTP')
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

    @patch('modularized.threads.notificationservice.requests.post')
    def test_notification_send_telegram(self, mock_post):
        """Test the internal logic of sending a Telegram message."""
        # Setup mock response
        mock_post.return_value = MagicMock(status_code=200)

        # Call the function
        service = NotificationService()
        chat_id = "123456789"
        message = "Hello Telegram"
        service.send_telegram_message(message, chat_id)

        # Assertions
        expected_url = f"https://api.telegram.org/bot{service.telegram_bot_token}/sendMessage"
        expected_payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        mock_post.assert_called_once_with(expected_url, json=expected_payload)

    @patch('modularized.shared.detection_manager.DetectionWorker')
    def test_detection_manager_round_robin(self, mock_worker):
        """Test that the DetectionManager distributes work in a round-robin fashion."""
        num_workers = 3
        manager = DetectionManager(num_workers)
        
        # Ensure workers were created
        self.assertEqual(len(manager.workers), num_workers)

        # Mock the submit method of the worker instances
        for worker in manager.workers:
            worker.submit = MagicMock()

        # Submit frames and check which worker gets the job
        frame1, camera1 = "frame1", "cam1"
        frame2, camera2 = "frame2", "cam2"
        frame3, camera3 = "frame3", "cam3"
        frame4, camera4 = "frame4", "cam4"

        manager.submit(frame1, camera1)
        manager.workers[0].submit.assert_called_once_with(frame1, camera1)
        manager.workers[1].submit.assert_not_called()
        manager.workers[2].submit.assert_not_called()

        manager.submit(frame2, camera2)
        manager.workers[1].submit.assert_called_once_with(frame2, camera2)

        manager.submit(frame3, camera3)
        manager.workers[2].submit.assert_called_once_with(frame3, camera3)

        # Fourth submission should go back to the first worker
        manager.submit(frame4, camera4)
        self.assertEqual(manager.workers[0].submit.call_count, 2)
        manager.workers[0].submit.assert_called_with(frame4, camera4)

        # Clean up singleton instance for other tests
        DetectionManager._instance = None


    @patch('modularized.database.psycopg2.connect')
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