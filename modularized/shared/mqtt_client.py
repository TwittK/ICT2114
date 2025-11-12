# shared/mqtt_client.py
import logging
import ssl
from datetime import datetime

import paho.mqtt.client as mqtt
import pytz
from shared.config import MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, MQTT_USERNAME, MQTT_PASSWORD


class MQTTClient:
    """Simple MQTT client to publish lab violation messages."""

    def __init__(
            self,
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            topic=MQTT_TOPIC,
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD
    ):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.username = username
        self.password = password

        # Create MQTT client.
        self.client = mqtt.Client()
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
            self.client.tls_set(tls_version=ssl.PROTOCOL_TLS)

        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
            logging.debug(f"📝 Connected to MQTT broker {self.broker}:{self.port}")
        except Exception as e:
            print(f"📝 Failed to connect to MQTT broker: {e}")

    def publish_violation(self, user, event, details=""):
        """Publish a violation message to the MQTT broker."""

        sgt = pytz.timezone("Asia/Singapore")
        timestamp = datetime.now(pytz.utc).astimezone(sgt).strftime("%d %b %Y %I:%M %p")
        print(f"MQTT {timestamp}")
        payload = f"[{timestamp}]\nUser: {user}\nEvent: {event}\nDetails: {details}"
        print(f"MQTT payload {payload}")

        try:
            self.client.publish(self.topic, payload)
            print(f"MQTT message sent:\n{payload}")
        except Exception as e:
            print(f"Failed to publish MQTT message: {e}")
