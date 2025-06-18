import json, os, pathlib, dataclasses
from typing import List, Optional

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")

@dataclasses.dataclass
class MqttSettings:
    enable: bool = True
    host: str = "mqtt"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    base_topic: str = "evcc/tesla"

@dataclasses.dataclass
class Vehicle:
    vin: Optional[str]
    host: str
    port: int = 6053
    password: Optional[str] = None
    encryption_key: Optional[str] = None

@dataclasses.dataclass
class Settings:
    log_level: str = "INFO"
    mqtt: MqttSettings = dataclasses.field(default_factory=MqttSettings)
    vehicles: List[Vehicle] = dataclasses.field(default_factory=list)


def load() -> Settings:
    path = pathlib.Path(CONFIG_FILE)
    if not path.is_file():
        raise RuntimeError("config.json not found")
    raw = json.loads(path.read_text())
    mqtt_raw = raw.get("mqtt", {})
    mqtt = MqttSettings(
        enable=mqtt_raw.get("enable", True),
        host=mqtt_raw.get("host", "mqtt"),
        port=int(mqtt_raw.get("port", 1883)),
        username=mqtt_raw.get("username"),
        password=mqtt_raw.get("password"),
        base_topic=mqtt_raw.get("base_topic", "evcc/tesla"),
    )
    vehicles = [
        Vehicle(
            vin=v.get("vin"),
            host=v["host"],
            port=int(v.get("port", 6053)),
            password=v.get("password"),
            encryption_key=v.get("encryption_key"),
        )
        for v in raw.get("vehicles", [])
    ]
    if not vehicles:
        raise RuntimeError("vehicles list empty")
    return Settings(log_level=raw.get("log_level", "INFO"), mqtt=mqtt, vehicles=vehicles) 