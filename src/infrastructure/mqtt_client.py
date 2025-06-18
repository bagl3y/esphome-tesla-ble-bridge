import logging
from typing import Callable
from paho.mqtt import client as mqtt_client

logger = logging.getLogger(__name__)

def init(settings) -> tuple[mqtt_client.Client | None, Callable[[str,str], None]]:
    if not settings.mqtt.enable:
        return None, lambda *_: None

    cli = mqtt_client.Client(client_id=f"tesla-ble-bridge")
    if settings.mqtt.username:
        cli.username_pw_set(settings.mqtt.username, settings.mqtt.password)

    def on_connect(_cli, _userdata, _flags, rc):
        if rc == 0:
            logger.info("MQTT connected to %s:%s", settings.mqtt.host, settings.mqtt.port)
        else:
            logger.error("MQTT connect failed rc=%s", rc)

    cli.on_connect = on_connect
    cli.loop_start()
    cli.connect_async(settings.mqtt.host, settings.mqtt.port, keepalive=60)

    def publish(topic_suffix: str, payload: str):
        topic = f"{settings.mqtt.base_topic}/{topic_suffix}" if not topic_suffix.startswith(settings.mqtt.base_topic) else topic_suffix
        cli.publish(topic, payload, retain=True)

    return cli, publish 