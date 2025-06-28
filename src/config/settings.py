import json, os, pathlib
from typing import List, Optional
from pydantic import BaseModel, Field, ValidationError

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.json")


class MqttSettings(BaseModel):
    enable: bool = True
    host: str = "mqtt"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    base_topic: str = "evcc/tesla"


class Vehicle(BaseModel):
    vin: Optional[str] = None
    host: str
    port: int = 6053
    password: Optional[str] = None
    encryption_key: Optional[str] = None


class Settings(BaseModel):
    log_level: str = "INFO"
    mqtt: MqttSettings = Field(default_factory=MqttSettings)
    vehicles: List[Vehicle]


def load() -> Settings:
    path = pathlib.Path(CONFIG_FILE)
    if not path.is_file():
        raise RuntimeError(f"Configuration file '{CONFIG_FILE}' not found at '{path.resolve()}'")
    
    try:
        raw_config = json.loads(path.read_text())
        settings = Settings.parse_obj(raw_config)

        if not settings.vehicles:
            raise RuntimeError("The 'vehicles' list in the configuration cannot be empty.")
            
        return settings
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Error decoding JSON from '{CONFIG_FILE}': {e}")
    except ValidationError as e:
        raise RuntimeError(f"Configuration validation error: {e}") 