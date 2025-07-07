import unittest
import requests
import time
import os
import sys
from unittest.mock import patch

# Simple black box tests that dont require Selenium (for easier local testing)
class BlackBoxFunctionalTests(unittest.TestCase):
    def setUp(self):
        self.base_url = "http://localhost:5000"
        self.session = requests.Session()

    def test_login_page_accessible(self):
        """Test that login page is accessible"""
        try:
            response = self.session.get(f"{self.base_url}/login")
            self.assertEqual(response.status_code, 200)
            self.assertIn("login", response.text.lower())
        except requests.exceptions.ConnectionError:
            self.skipTest("Flask app not running. Start app with 'python app.py' first.")

    def test_login_with_valid_credentials(self):
        """Test login with valid admin credentials"""
        try:
            response = self.session.post(f"{self.base_url}/login", data={
                'email': 'admin@labcomply.com',
                'password': 'admin123'
            })
            # Should redirect (302) or succeed (200)
            self.assertIn(response.status_code, [200, 302])
        except requests.exceptions.ConnectionError:
            self.skipTest("Flask app not running. Start app with 'python app.py' first.")

    def test_login_with_invalid_credentials(self):
        """Test login with invalid credentials"""
        try:
            response = self.session.post(f"{self.base_url}/login", data={
                'email': 'invalid@test.com',
                'password': 'wrongpassword'
            })
            # Should stay on login page or show error
            self.assertEqual(response.status_code, 200)
            self.assertIn("login", response.text.lower())
        except requests.exceptions.ConnectionError:
            self.skipTest("Flask app not running. Start app with 'python app.py' first.")

    def test_protected_route_redirect(self):
        """Test that protected routes redirect to login"""
        try:
            response = self.session.get(f"{self.base_url}/", allow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response.headers.get("Location", "").lower())
        except requests.exceptions.ConnectionError:
            self.skipTest("Flask app not running. Start app with 'python app.py' first.")

class BlackBoxSecurityTests(unittest.TestCase):
    def setUp(self):
        self.base_url = "http://localhost:5000"
        self.session = requests.Session()

    def test_sql_injection_in_login(self):
        """Test SQL injection attempts in login form"""
        injection_payloads = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "admin@labcomply.com'; DELETE FROM users; --"
        ]
        
        for payload in injection_payloads:
            with self.subTest(payload=payload):
                try:
                    response = self.session.post(f"{self.base_url}/login", data={
                        'email': payload,
                        'password': 'test'
                    })
                    # Should not cause server errors
                    self.assertNotEqual(response.status_code, 500)
                except requests.exceptions.ConnectionError:
                    self.skipTest("Flask app not running. Start app with 'python app.py' first.")

    def test_xss_in_login_form(self):
        """Test XSS attempts in login form"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>"
        ]
        
        for payload in xss_payloads:
            with self.subTest(payload=payload):
                try:
                    response = self.session.post(f"{self.base_url}/login", data={
                        'email': payload,
                        'password': 'test'
                    })
                    # Should not execute script or cause errors
                    self.assertNotEqual(response.status_code, 500)
                    self.assertNotIn("<script>", response.text)
                except requests.exceptions.ConnectionError:
                    self.skipTest("Flask app not running. Start app with 'python app.py' first.")

if __name__ == '__main__':
    unittest.main()