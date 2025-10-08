# shared/mqtt_client.py
from datetime import datetime
import paho.mqtt.publish as publish

from shared.config import MQTT_PORT, MQTT_BROKER, MQTT_TOPIC_VIOLATIONS


class MQTTClient:
    """Simple MQTT client to publish lab violation messages."""

    def __init__(self, broker=MQTT_BROKER, port=MQTT_PORT, topic=MQTT_TOPIC_VIOLATIONS):
        self.broker = broker
        self.port = port
        self.topic = topic

    def publish_violation(self, user, event, details=""):
        """Publish a violation message to the MQTT broker."""
        timestamp = datetime.now().strftime("%d %b %Y %I:%M %p")
        payload = f"[{timestamp}]\nUser: {user}\nEvent: {event}\nDetails: {details}"

        try:
            publish.single(self.topic, payload=payload, hostname=self.broker, port=self.port)
            print(f"MQTT message sent:\n{payload}")
        except Exception as e:
            print(f"Failed to publish MQTT message: {e}")
