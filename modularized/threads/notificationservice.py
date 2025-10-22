import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import os

class NotificationService:
    def __init__(self):
        
        # Email Setup
        self.gmail_smtp_host = "smtp.gmail.com"
        self.gmail_smtp_port = 587
        self.sender_email = "sitlabincompliance@gmail.com"  # Replace with your Gmail
        self.sender_password = "drky unyj nmxu zqeb"  # Use App Password from Google

        # Telegram Setup
        self.telegram_bot_token = "8272893365:AAGUVKaxPHvgD970Xbv_VGeS31RxAnM9nUE"
        self.telegram_chat_id = "307852371"

    # ---------- EMAIL ----------
    def send_email(self, to_email, subject, body):
        try:
            # Setup the MIME
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = to_email
            msg['Subject'] = subject

            # Add body content to email
            msg.attach(MIMEText(body, 'plain'))

            # Set up the server
            server = smtplib.SMTP(self.gmail_smtp_host, self.gmail_smtp_port)
            server.starttls()  # Use TLS to encrypt the connection
            server.login(self.sender_email, self.sender_password)

            # Send the email
            text = msg.as_string()
            server.sendmail(self.sender_email, to_email, text)
            server.quit()

            print(f"Email sent to {to_email}")

        except Exception as e:
            print(f"Error sending email: {e}")

    def send_incompliance_email(self, to_email, person_name):
        """
        Sends an "Incompliance Detected" notification email to the specified recipient.

        Parameters:
            to_email (str): Recipient email address.
            person_name (str): Name of the person detected to be non-compliant.
        """
        subject = f"Incompliance Detected for {person_name}"
        body = f"Dear Lab Safety Staff,\n\nAn incompliance was detected for {person_name}. Please check the system for further details."
        self.send_email(to_email, subject, body)

    # ---------- TELEGRAM ----------
    def send_telegram_message(self, message):
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {"chat_id": self.telegram_chat_id, "text": message}

        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()
            print("✅ Telegram message sent")
        except requests.exceptions.RequestException as e:
            print(f"❌ Error sending Telegram message: {e}")

    def send_incompliance_telegram(self, person_name, camera_id):
        message = (
            f"🚨 *Incompliance Detected*\n"
            f"👤 Person: {person_name}\n"
            f"📍 Camera ID: {camera_id}\n"
            f"🕒 Please check the dashboard for full details."
        )
        self.send_telegram_message(message)