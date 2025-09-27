import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import os

class EmailService:

    def __init__(self):
        """
        Initializes the EmailService with Gmail SMTP settings and sender credentials.
        """
        self.gmail_smtp_host = "smtp.gmail.com"
        self.gmail_smtp_port = 587
        self.sender_email = "sitlabincompliance@gmail.com"  # Replace with your Gmail
        self.sender_password = "drky unyj nmxu zqeb"  # Use App Password from Google

    def send_email(self, to_email, subject, body):
        """
        Sends an email using Gmail's SMTP server.

        Parameters:
            to_email (str): Recipient email address.
            subject (str): Subject line of the email.
            body (str): Plain text body content of the email.

        Raises:
            Exception: If sending the email fails, an error message will be printed.
        """
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
