import json, os, dataclasses, pathlib
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
    mqtt: MqttSettings = MqttSettings()
    vehicles: List[Vehicle] = dataclasses.field(default_factory=list)


def load_settings() -> Settings:
    cfg_path = pathlib.Path(CONFIG_FILE)
    if not cfg_path.is_file():
        raise RuntimeError(f"Config file {cfg_path} not found")
    raw = json.loads(cfg_path.read_text())

    mqtt_cfg = raw.get("mqtt", {})
    mqtt = MqttSettings(
        enable=mqtt_cfg.get("enable", True),
        host=mqtt_cfg.get("host", "mqtt"),
        port=int(mqtt_cfg.get("port", 1883)),
        username=mqtt_cfg.get("username"),
        password=mqtt_cfg.get("password"),
        base_topic=mqtt_cfg.get("base_topic", "evcc/tesla"),
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
        raise RuntimeError("'vehicles' array must contain at least one entry")

    return Settings(
        log_level=raw.get("log_level", "INFO"),
        mqtt=mqtt,
        vehicles=vehicles,
    ) 