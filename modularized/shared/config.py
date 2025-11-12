# shared/config.py

import os

# --- MQTT Configuration ---
MQTT_BROKER = os.environ.get("MQTT_BROKER", "hivemq")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 8883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "lab/violations")
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")

GMAIL_PASSKEY = os.environ.get("GMAIL_PASSKEY")

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# --- Live Feed, First non-compliance, Second and more non-compliance Pagination page ---
LF_CAMERA_PER_PAGE = 1
FINC_CAMERA_PER_PAGE = 3
SINC_CAMERA_PER_PAGE = 3
