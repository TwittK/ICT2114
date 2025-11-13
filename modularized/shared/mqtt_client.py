# shared/mqtt_client.py
import logging
import ssl
from datetime import datetime

import paho.mqtt.client as mqtt
import pytz
from shared.config import MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, MQTT_USERNAME, MQTT_PASSWORD


class MQTTClient:
    """
    Simple MQTT client to publish lab violation messages.

    This class wraps connection setup and message publishing for MQTT.
    It supports TLS, username/password authentication, and publishes
    formatted violation messages to a configured topic.

    Attributes:
        broker (str): MQTT broker address.
        port (int): MQTT broker port.
        topic (str): MQTT topic to publish to.
        username (str): Username for MQTT authentication.
        password (str): Password for MQTT authentication.
        client (mqtt.Client): The underlying paho-mqtt client instance.
    """

    def __init__(
            self,
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            topic=MQTT_TOPIC,
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD
    ):
        """
        Initialise the MQTT client and connect to the broker.

        Parameters:
            broker (str): MQTT broker address.
            port (int): MQTT broker port.
            topic (str): MQTT topic to publish to.
            username (str): Username for MQTT authentication.
            password (str): Password for MQTT authentication.
        """
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
        """
        Publish a violation message to the MQTT broker.

        Parameters:
            user (str): Username or identifier of the violator.
            event (str): Description of the violation event.
            details (str, optional): Additional details about the violation.

        Returns:
            None
        """
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
