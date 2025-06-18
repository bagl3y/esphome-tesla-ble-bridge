import logging
from paho.mqtt import client as mqtt_client
from src.config.settings import Settings

log = logging.getLogger(__name__)

def init(settings: Settings):
    if not settings.mqtt.enable:
        return None, lambda *_: None

    cli = mqtt_client.Client()
    if settings.mqtt.username:
        cli.username_pw_set(settings.mqtt.username, settings.mqtt.password)

    def on_connect(c, *_):
        if c.is_connected():
            log.info("MQTT connected")
    cli.on_connect = on_connect
    cli.loop_start()
    cli.connect_async(settings.mqtt.host, settings.mqtt.port, 60)

    def publish_simple(name: str, payload: str):
        cli.publish(f"{settings.mqtt.base_topic}/{name}", payload, retain=True)

    return cli, publish_simple 