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
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        # Return a row to indicate permission exists
        mock_cursor.fetchone.return_value = (1,)  # Returns a tuple with a value
        
        result = check_permission('admin', 'camera_management')
        
        self.assertTrue(result)
        mock_cursor.execute.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('web.utils.psycopg2.connect')
    def test_check_permission_denied(self, mock_connect):
        """Test the check_permission function when permission is denied."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        # Return None to indicate no permission found
        mock_cursor.fetchone.return_value = None
        
        result = check_permission('user', 'camera_management')
        
        self.assertFalse(result)
        mock_cursor.execute.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_validate_and_sanitize_text_valid(self):
        """Test validate_and_sanitize_text with valid input."""
        result = validate_and_sanitize_text("Hello World")
        self.assertEqual(result, "Hello World")

    def test_validate_and_sanitize_text_with_html(self):
        """Test that HTML tags are stripped."""
        result = validate_and_sanitize_text("<b>Bold</b> text")
        self.assertEqual(result, "Bold text")

    def test_validate_and_sanitize_text_too_long(self):
        """Test input that is too long."""
        with self.assertRaises(ValueError) as context:
            validate_and_sanitize_text("A" * 101)
        self.assertIn("between 1 and 100", str(context.exception))

    def test_validate_and_sanitize_text_empty(self):
        """Test empty input after stripping whitespace."""
        with self.assertRaises(ValueError) as context:
            validate_and_sanitize_text("   ")
        self.assertIn("between 1 and 100", str(context.exception))

    def test_validate_and_sanitize_text_not_string(self):
        """Test non-string input."""
        with self.assertRaises(ValueError) as context:
            validate_and_sanitize_text(12345)
        self.assertIn("must be a string", str(context.exception))

    @patch('threads.notificationservice.smtplib.SMTP')
    def test_notification_send_email(self, mock_smtp):
        """Test the internal logic of sending an email."""
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        service = NotificationService()
        service.send_email('recipient@example.com', 'Test Subject', 'Test Body')
        
        mock_smtp.assert_called_once_with(service.gmail_smtp_host, service.gmail_smtp_port)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(service.sender_email, service.sender_password)
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch('threads.notificationservice.requests.post')
    def test_notification_send_telegram(self, mock_post):
        """Test the internal logic of sending a Telegram message."""
        mock_post.return_value.status_code = 200

        service = NotificationService()
        service.send_telegram_message('Hello Telegram', chat_id='123456789')

        expected_url = f'https://api.telegram.org/bot{service.telegram_bot_token}/sendMessage'
        expected_payload = {
            'chat_id': '123456789',
            'text': 'Hello Telegram',
            'parse_mode': 'Markdown'
        }

        mock_post.assert_called_once_with(expected_url, data=expected_payload)

    @patch('database.psycopg2.connect')
    def test_create_user_role_not_found(self, mock_connect):
        """Test create_user when the specified role does not exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        
        # Expect ValueError to be raised instead of False return
        with self.assertRaises(ValueError) as context:
            create_user('testuser', 'test@example.com', 'password', 'nonexistent_role')
        
        self.assertIn('does not exist', str(context.exception))
        mock_conn.close.assert_called_once()

    @patch('shared.detection_manager.DetectionWorker')
    def test_detection_manager_round_robin(self, MockWorker):
        """Test that the DetectionManager distributes work in a round-robin fashion."""
        # Create mock worker instances with submit method
        mock_workers = []
        for i in range(3):
            mock_worker = MagicMock()
            mock_worker.submit = MagicMock()
            mock_workers.append(mock_worker)
        
        MockWorker.side_effect = mock_workers
        
        num_workers = 3
        # Reset the singleton instance for testing
        DetectionManager._instance = None
        manager = DetectionManager(num_workers=num_workers)

        # Verify the manager created the correct number of workers
        self.assertEqual(len(manager.workers), num_workers)
        
        # Verify that the workers in the manager are our mocks
        for i in range(num_workers):
            self.assertIs(manager.workers[i], mock_workers[i])

        # Submit frames
        manager.submit('frame1', 'cam1')
        manager.submit('frame2', 'cam2')
        manager.submit('frame3', 'cam3')
        manager.submit('frame4', 'cam4')

        # Verify round-robin distribution
        # Worker 0 should get frames 1 and 4
        self.assertEqual(mock_workers[0].submit.call_count, 2)
        mock_workers[0].submit.assert_any_call('frame1', 'cam1')
        mock_workers[0].submit.assert_any_call('frame4', 'cam4')

        # Worker 1 should get frame 2
        self.assertEqual(mock_workers[1].submit.call_count, 1)
        mock_workers[1].submit.assert_called_with('frame2', 'cam2')

        # Worker 2 should get frame 3
        self.assertEqual(mock_workers[2].submit.call_count, 1)
        mock_workers[2].submit.assert_called_with('frame3', 'cam3')

        # Verify the index wrapped around correctly
        self.assertEqual(manager.next_worker_index, 1)


if __name__ == '__main__':
    unittest.main()