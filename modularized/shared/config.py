# shared/config.py

import os

# --- MQTT Configuration ---
MQTT_BROKER = os.environ.get("MQTT_BROKER", "hivemq")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 8883))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "lab/violations")
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
