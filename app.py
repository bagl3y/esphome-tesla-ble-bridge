"""Tesla BLE bridge: ESPHome -> HTTP/MQTT

This service connects to an ESPHome device (running tesla-ble firmware)
and exposes selected entities via HTTP (FastAPI) and, optionally, MQTT.
All runtime configuration is taken from environment variables so the
container can be configured easily via docker-compose.
"""

from __future__ import annotations

import asyncio
import logging
import os
import json
from contextlib import suppress
from typing import Any, Dict, Optional
from pathlib import Path

import aioesphomeapi
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import JSONResponse
from paho.mqtt import client as mqtt_client

# ---------------------------------------------------------------------------
# Configuration (file + env) ------------------------------------------------
# ---------------------------------------------------------------------------

load_dotenv()

# 1) Charge du fichier JSON pointé par $CONFIG_FILE (défaut config.json)
CONFIG_PATH = os.getenv("CONFIG_FILE", "config.json")
_CONF: dict[str, Any] = {}
if Path(CONFIG_PATH).is_file():
    try:
        _CONF = json.loads(Path(CONFIG_PATH).read_text())
    except Exception as err:  # noqa: BLE001
        raise RuntimeError(f"Unable to parse config file {CONFIG_PATH}: {err}")


# Helper pour lire la conf avec fallback env -> valeur par défaut

def _conf(path: str, default=None):  # type: ignore[return-value]
    """Return value from config dict or default."""
    cur: Any = _CONF
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


# Logging doit être initialisé après lecture de log_level

logging.basicConfig(
    level=str(_conf("log_level", "INFO")).upper(),
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Runtime configuration ------------------------------------------------------
# ----------------------------------------------------------------------------

def _env(key: str, default: Optional[str] = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise RuntimeError(f"Required env var {key} is missing")
    return value

def _load_vehicles() -> list[dict[str, Any]]:
    """Return list of vehicles from config file.

    Le fichier JSON doit contenir une clé "vehicles" avec un tableau d'objets.
    """
    vehicles_from_file = _conf("vehicles")
    if not isinstance(vehicles_from_file, list) or not vehicles_from_file:
        raise RuntimeError("Missing 'vehicles' array in config.json")
    return vehicles_from_file

_VEHICLES = _load_vehicles()

# Default VIN (utilisé pour routes non Fleet)
DEFAULT_VIN = _VEHICLES[0].get("vin") or "default"

# MQTT (optional)
_mqtt_cfg = _conf("mqtt", {}) or {}
MQTT_ENABLE = bool(_mqtt_cfg.get("enable", True))
MQTT_HOST = _mqtt_cfg.get("host", "mqtt")
MQTT_PORT = int(_mqtt_cfg.get("port", 1883))
MQTT_USERNAME = _mqtt_cfg.get("username")
MQTT_PASSWORD = _mqtt_cfg.get("password")
MQTT_BASE_TOPIC = _mqtt_cfg.get("base_topic", "evcc/tesla")

# Mapping between ESPHome entity keys and exposed names (HTTP/MQTT)
ENTITY_MAP: dict[str, str] = {
    # key in ESPHome -> simplified name to expose
    "battery_level": "soc",
    "connected": "connected",
    "charging": "charging",
}

# ----------------------------------------------------------------------------
# Global state ---------------------------------------------------------------
# ----------------------------------------------------------------------------

# Current values for each entity key
_state: Dict[str, Any] = {}
# Full entity metadata   key -> msg
_entities: Dict[str, aioesphomeapi.ListEntitiesResponse] = {}
# Map key -> platform/type (sensor, button, number, switch ...)
_entity_types: Dict[str, str] = {}
# Map object_id -> key for quick lookup
_oid_to_key: Dict[str, str] = {}

_state_lock = asyncio.Lock()

# MQTT client is optional, will be initialised at runtime
_mqtt: Optional[mqtt_client.Client] = None

# ----------------------------------------------------------------------------
# ESPHome handling -----------------------------------------------------------
# ----------------------------------------------------------------------------

async def _handle_state(state: aioesphomeapi.StateResponse) -> None:  # type: ignore[name-defined]
    """Callback for every state update from ESPHome."""
    async with _state_lock:
        _state[state.key] = state.state
    human_key = ENTITY_MAP.get(state.key)
    if human_key and _mqtt:
        topic = f"{MQTT_BASE_TOPIC}/{human_key}"
        payload = str(state.state)
        _mqtt.publish(topic, payload, retain=True)
        logger.debug("Published %s -> %s", topic, payload)


async def _esp_loop() -> None:
    """Main loop: maintain connection and subscribe to states."""
    password_arg = _VEHICLES[0]["password"] or ""
    client_kwargs = {}
    if _VEHICLES[0]["encryption_key"]:
        client_kwargs["noise_psk"] = _VEHICLES[0]["encryption_key"]

    client = aioesphomeapi.APIClient(_VEHICLES[0]["host"], _VEHICLES[0]["port"], password_arg, **client_kwargs)

    while True:
        try:
            logger.info("Connecting to ESPHome device %s:%s ...", _VEHICLES[0]["host"], _VEHICLES[0]["port"])
            await client.connect(login=True)
            globals()["_last_client"] = client  # expose client to API routes
            logger.info("Connected, subscribing to states ...")

            # Initial data
            device_info = await client.device_info()
            logger.info("Device: %s running ESPHome %s", device_info.name, device_info.esphome_version)

            # Retrieve entity definitions once after login
            ent_res = await client.list_entities_services()
            if isinstance(ent_res, tuple):
                ent_list = ent_res[0]
            else:
                ent_list = ent_res
            for ent_msg in ent_list:
                _entities[ent_msg.key] = ent_msg

                # detect platform
                raw_name = ent_msg.__class__.__name__
                platform = raw_name.replace("ListEntities", "").replace("Response", "").lower()
                # Newer ESPHome versions utilisent *Info messages
                if platform.endswith("info"):
                    platform = platform[:-4]  # supprime "info"
                # Par cohérence, on supprime le suffixe "sensor" si présent (binarysensor -> binary_sensor)
                if platform.endswith("sensor") and not platform.endswith("_sensor"):
                    platform = platform[:-6] + "_sensor"

                _entity_types[ent_msg.key] = platform

                if getattr(ent_msg, "object_id", None):
                    _oid_to_key[ent_msg.object_id] = ent_msg.key
                logger.debug(
                    "Discovered entity key=%s name=%s type=%s", ent_msg.key, ent_msg.name, ent_msg.__class__.__name__
                )

            # Register state callback
            def _state_cb(state) -> None:  # callback normal
                asyncio.create_task(_handle_state(state))

            client.subscribe_states(_state_cb)

            # Wait until the connection is dropped (library >=32.0.0) otherwise sleep forever
            try:
                await client.wait_until_disconnected()  # type: ignore[attr-defined]
            except AttributeError:
                await asyncio.Future()  # never completes

        except aioesphomeapi.APIConnectionError as err:
            logger.warning("Connection error (%s). Reconnecting in 10 s ...", err)
            await client.disconnect()
            await asyncio.sleep(10)
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error in ESP loop")
            await asyncio.sleep(10)


# ----------------------------------------------------------------------------
# MQTT handling --------------------------------------------------------------
# ----------------------------------------------------------------------------

def _init_mqtt(loop: asyncio.AbstractEventLoop) -> Optional[mqtt_client.Client]:  # noqa: D401
    """Initialize an asynchronous MQTT client (in background thread)."""
    if not MQTT_ENABLE:
        logger.info("MQTT disabled in config.json")
        return None

    client_id = f"tesla-ble-bridge-{os.getpid()}"

    cli = mqtt_client.Client(client_id=client_id)

    if MQTT_USERNAME:
        cli.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # Connect in blocking manner (with timeout)
    def _on_connect(_cli, _userdata, flags, rc):  # noqa: D401, ANN001
        if rc == 0:
            logger.info("MQTT connected to %s:%s", MQTT_HOST, MQTT_PORT)
        else:
            logger.error("Failed to connect to MQTT broker: rc=%s", rc)

    cli.on_connect = _on_connect

    # run network loop in background thread
    cli.loop_start()

    cli.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)

    return cli


# ----------------------------------------------------------------------------
# FastAPI web application -----------------------------------------------------
# ----------------------------------------------------------------------------

app = FastAPI(title="Tesla BLE Bridge", version="0.1.0")


@app.on_event("startup")
async def _startup_event() -> None:
    loop = asyncio.get_event_loop()

    # Start MQTT
    global _mqtt  # noqa: PLW0603
    _mqtt = _init_mqtt(loop)

    # Start ESP loop
    loop.create_task(_esp_loop())


@app.on_event("shutdown")
async def _shutdown_event() -> None:
    if _mqtt:
        logger.info("Closing MQTT client ...")
        with suppress(Exception):
            _mqtt.loop_stop()
            _mqtt.disconnect()


# ----------------------------- HTTP routes ----------------------------------


def _get_state_value(key: str) -> Any:
    # d'abord clé exacte (str)
    if key in _state:
        return _state[key]

    # object_id -> clé numérique
    num_key = _oid_to_key.get(key)
    if num_key is not None:
        return _state.get(num_key)

    # clé numérique passée en clair
    if key.isdigit():
        return _state.get(int(key))

    return None


@app.get("/state/{name}")
async def get_state(name: str) -> JSONResponse:  # noqa: D401
    """Return raw value for a given ESPHome entity key."""
    async with _state_lock:
        value = _get_state_value(name)
    if value is None:
        raise HTTPException(status_code=404, detail="Unknown state")
    return JSONResponse(content={"name": name, "value": value})


@app.get("/entities")
async def list_entities() -> JSONResponse:  # noqa: D401
    """Return list of discovered entities with basic metadata."""
    async with _state_lock:
        entities_list = [
            {
                "key": key,
                "name": ent.name,
                "object_id": getattr(ent, "object_id", None),
                "unit": getattr(ent, "unit_of_measurement", None),
                "platform": _entity_types.get(key),
                "device_class": getattr(ent, "device_class", None),
                "state": _state.get(key),
            }
            for key, ent in _entities.items()
        ]
    return JSONResponse(content=entities_list)


# ---------------------------------------------------------------------------
# Helper: get ESP key from object_id
# ---------------------------------------------------------------------------


def _lookup_key(object_id: str) -> Optional[str]:
    return _oid_to_key.get(object_id)


# ------------------------- Action / Command routes -------------------------


def _client_connected(client: aioesphomeapi.APIClient) -> bool:  # type: ignore[name-defined]
    """Return True si le client est connecté, quelle que soit la version de la lib."""
    # Nouveau : propriété booléenne
    if hasattr(client, "is_connected") and not callable(getattr(client, "is_connected")):
        return bool(getattr(client, "is_connected"))
    # Ancienne version : méthode
    if hasattr(client, "is_connected") and callable(getattr(client, "is_connected")):
        try:
            return bool(client.is_connected())  # type: ignore[operator]
        except Exception:  # noqa: BLE001
            return False
    # fallback attribut protégé
    return getattr(client, "_connected", False)


def _ensure_client() -> aioesphomeapi.APIClient:  # type: ignore[return-value]
    client = globals().get("_last_client")
    if client is None:
        raise HTTPException(503, "ESPHome client not connected")
    return client


@app.post("/button/{object_id}/press")
async def press_button(object_id: str) -> JSONResponse:  # noqa: D401
    key = _lookup_key(object_id)
    if not key:
        raise HTTPException(404, "Unknown button object_id")
    if _entity_types.get(key) != "button":
        raise HTTPException(400, "Entity is not a button")

    client = _ensure_client()
    try:
        await _call_api(client, "button_command", key)
    except Exception as err:  # noqa: BLE001
        logger.warning("Button press failed: %s", err)
        raise HTTPException(503, "ESPHome client not connected or command failed")
    return JSONResponse(content={"pressed": object_id})


@app.post("/switch/{object_id}")
async def set_switch(object_id: str, state: bool) -> JSONResponse:  # noqa: D401
    key = _lookup_key(object_id)
    if not key:
        raise HTTPException(404, "Unknown switch object_id")
    if _entity_types.get(key) != "switch":
        raise HTTPException(400, "Entity is not a switch")

    client = _ensure_client()
    try:
        await _call_api(client, "switch_command", key, state)
    except Exception as err:  # noqa: BLE001
        logger.warning("Switch set failed: %s", err)
        raise HTTPException(503, "ESPHome client not connected or command failed")
    return JSONResponse(content={"state": state})


@app.post("/number/{object_id}")
async def set_number(object_id: str, value: float) -> JSONResponse:  # noqa: D401
    key = _lookup_key(object_id)
    if not key:
        raise HTTPException(404, "Unknown number object_id")
    if _entity_types.get(key) != "number":
        raise HTTPException(400, "Entity is not a number")

    client = _ensure_client()
    try:
        await _call_api(client, "number_command", key, value)
    except Exception as err:  # noqa: BLE001
        logger.warning("Number set failed: %s", err)
        raise HTTPException(503, "ESPHome client not connected or command failed")
    return JSONResponse(content={"value": value})


# ---------------------- Dedicated EV routes ----------------------


# batterie (%)


@app.get("/vehicle/battery")
async def vehicle_battery() -> JSONResponse:  # noqa: D401
    async with _state_lock:
        val = _get_state_value("charge_level")
    return JSONResponse(content={"battery_pct": val})


# wake-up (button)


@app.post("/vehicle/wake_up")
async def vehicle_wake() -> JSONResponse:  # noqa: D401
    key = _lookup_key("wake_up")
    if not key:
        raise HTTPException(404, "wake_up button not found")
    client = _ensure_client()
    func = getattr(client, "button_command")
    if asyncio.iscoroutinefunction(func):
        await func(key)
    else:
        func(key)
    return JSONResponse(content={"pressed": "wake_up"})


# charger ON/OFF (switch)


@app.post("/vehicle/charger")
async def vehicle_charger(state: bool) -> JSONResponse:  # noqa: D401
    key = _lookup_key("charger")
    if not key:
        raise HTTPException(404, "charger switch not found")
    client = _ensure_client()
    await _call_api(client, "switch_command", key, state)
    return JSONResponse(content={"state": state})


# courant de charge (A) numéro


@app.post("/vehicle/charging_amps")
async def vehicle_charging_amps(value: float) -> JSONResponse:  # noqa: D401
    key = _lookup_key("charging_amps")
    if not key:
        raise HTTPException(404, "charging_amps number not found")
    client = _ensure_client()
    await _call_api(client, "number_command", key, value)
    return JSONResponse(content={"value": value})


# limite de charge (%) numéro


@app.post("/vehicle/charging_limit")
async def vehicle_charging_limit(value: float) -> JSONResponse:  # noqa: D401
    key = _lookup_key("charging_limit")
    if not key:
        raise HTTPException(404, "charging_limit number not found")
    client = _ensure_client()
    await _call_api(client, "number_command", key, value)
    return JSONResponse(content={"value": value})


# ---------------------------------------------------------------------------
# Helper pour appeler une méthode API sync ou async indifféremment
# ---------------------------------------------------------------------------


async def _call_api(client: Any, method: str, *args) -> None:  # noqa: ANN401
    func = getattr(client, method)
    if asyncio.iscoroutinefunction(func):
        await func(*args)
    else:
        func(*args)


# ---------------------------------------------------------------------------
# Tesla Fleet compatible API layer ------------------------------------------
# ---------------------------------------------------------------------------

# Helper to wrap answers in { "response": ... } like the Fleet API

def _fleet_resp(data: dict | list):
    """Return JSONResponse with a top-level 'response' key (Fleet style)."""
    return JSONResponse(content={"response": data})


# Mapping between Fleet command names and internal helper functions -----------

async def _cmd_wake_up(body: dict[str, Any] | None = None) -> None:
    await vehicle_wake()


async def _cmd_charge_start(body: dict[str, Any] | None = None) -> None:
    await vehicle_charger(True)


async def _cmd_charge_stop(body: dict[str, Any] | None = None) -> None:
    await vehicle_charger(False)


async def _cmd_set_charging_amps(body: dict[str, Any] | None) -> None:
    if not body or "charging_amps" not in body:
        raise HTTPException(400, "Missing 'charging_amps' in body")
    await vehicle_charging_amps(float(body["charging_amps"]))


async def _cmd_set_charge_limit(body: dict[str, Any] | None) -> None:
    # Tesla spec uses "percent" in examples, fallback to charge_limit key too
    if not body:
        raise HTTPException(400, "Missing body JSON with charge limit")
    percent = body.get("percent") or body.get("charge_limit") or body.get("charging_limit")
    if percent is None:
        raise HTTPException(400, "Missing 'percent' in body")
    await vehicle_charging_limit(float(percent))


# Registry of supported commands
_FLEET_COMMANDS: dict[str, Any] = {
    "wake_up": _cmd_wake_up,
    "charge_start": _cmd_charge_start,
    "charge_stop": _cmd_charge_stop,
    "set_charging_amps": _cmd_set_charging_amps,
    "set_charge_limit": _cmd_set_charge_limit,
    # ---- Nouveaux liens Fleet -> entités ----
    "auto_conditioning_start": lambda body=None: _generic_entity_command("climate", {"state": True}),
    "auto_conditioning_stop": lambda body=None: _generic_entity_command("climate", {"state": False}),
    "charge_port_door_open": lambda body=None: _generic_entity_command("charge_port", {"state": True}),
    "charge_port_door_close": lambda body=None: _generic_entity_command("charge_port", {"state": False}),
    "flash_lights": lambda body=None: _generic_entity_command("flash_light", None),
    "honk_horn": lambda body=None: _generic_entity_command("sound_horn", None),
    "unlock_charge_port": lambda body=None: _generic_entity_command("unlock_charge_port", None),
    "set_sentry_mode": None,  # placeholder, handled below
}


@app.post("/api/1/vehicles/{vin}/command/{command}")
async def fleet_command(  # noqa: D401
    vin: str,
    command: str,
    wait: bool = Query(False),
    body: Optional[dict[str, Any]] = Body(None),
) -> JSONResponse:
    """Implement subset of Tesla Fleet /command/* endpoints.

    The VIN is currently ignored and accepted for compatibility.
    """
    # validate VIN if configured
    cfg_vin = (_VEHICLES[0].get("vin") or "").upper()
    if cfg_vin and vin.upper() != cfg_vin:
        raise HTTPException(404, "Unknown vehicle VIN")

    cmd_fn = _FLEET_COMMANDS.get(command)
    if not cmd_fn:
        # fallback dynamic entity command
        cmd_fn = _generic_entity_command

    # Execute command
    try:
        # generic handler needs command name param
        if cmd_fn is _generic_entity_command:
            await cmd_fn(command, body)
        else:
            await cmd_fn(body)
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        logger.warning("Fleet command %s failed: %s", command, err)
        raise HTTPException(503, "Command failed or ESP not connected")

    # Optionally wait until condition met (best-effort)
    if wait and command in {"charge_start", "charge_stop"}:
        target_charging = command == "charge_start"
        for _ in range(10):  # up to ~10 s
            await asyncio.sleep(1)
            async with _state_lock:
                if bool(_get_state_value("charging")) == target_charging:
                    break

    return _fleet_resp({"result": True})


# ------------------------ Vehicle data endpoint -----------------------------


def _build_charge_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return dict mimicking Fleet API 'charge_state' using a state snapshot."""
    return {
        "battery_level": snapshot.get("battery_level"),
        "charge_port_door_open": snapshot.get("charge_port_door_open"),
        "charging_state": "Charging" if snapshot.get("charging") else "Stopped",
        "charge_limit_soc": snapshot.get("charging_limit"),
        "charge_current_request": snapshot.get("charging_amps"),
    }


def _build_climate_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return minimal climate_state placeholder using a state snapshot."""
    return {
        "inside_temp": snapshot.get("inside_temp"),
        "outside_temp": snapshot.get("outside_temp"),
        "is_auto_conditioning_on": snapshot.get("is_auto_conditioning_on"),
    }


@app.get("/api/1/vehicles/{vin}/vehicle_data")
async def fleet_vehicle_data(  # noqa: D401
    vin: str,
    endpoints: Optional[str] = Query(None, description="Comma-separated list of endpoints to include"),
) -> JSONResponse:
    """Return vehicle data similar to Fleet API.

    Supported endpoints: charge_state, climate_state
    """
    cfg_vin = (_VEHICLES[0].get("vin") or "").upper()
    if cfg_vin and vin.upper() != cfg_vin:
        raise HTTPException(404, "Unknown vehicle VIN")

    requested = set(ep.strip() for ep in endpoints.split(",")) if endpoints else {"charge_state", "climate_state"}

    async with _state_lock:
        snapshot = dict(_state)

    resp: dict[str, Any] = {}
    if "charge_state" in requested:
        resp["charge_state"] = _build_charge_state(snapshot)
    if "climate_state" in requested:
        resp["climate_state"] = _build_climate_state(snapshot)

    return _fleet_resp(resp)


# -------------------- Body controller state endpoint ------------------------

@app.get("/api/1/vehicles/{vin}/body_controller_state")
async def fleet_body_controller_state(vin: str) -> JSONResponse:  # noqa: D401
    """Return body controller state similar to Fleet API."""
    cfg_vin = (_VEHICLES[0].get("vin") or "").upper()
    if cfg_vin and vin.upper() != cfg_vin:
        raise HTTPException(404, "Unknown vehicle VIN")

    async with _state_lock:
        locked = _get_state_value("vehicle_locked")  # example ESP sensor
        asleep = not bool(_get_state_value("connected"))

    data = {
        "vehicleLockState": "VEHICLELOCKSTATE_LOCKED" if locked else "VEHICLELOCKSTATE_UNLOCKED",
        "vehicleSleepStatus": "VEHICLE_SLEEP_STATUS_ASLEEP" if asleep else "VEHICLE_SLEEP_STATUS_AWAKE",
        "userPresence": "VEHICLE_USER_PRESENCE_UNKNOWN",
    }
    return _fleet_resp(data)


# ---------------------------- Proxy version ---------------------------------

@app.get("/api/proxy/1/version")
async def fleet_proxy_version() -> JSONResponse:  # noqa: D401
    return _fleet_resp({"version": app.version})


# -------------------- Generic dynamic command handler ----------------------

async def _generic_entity_command(name: str, body: dict[str, Any] | None) -> None:
    """Try to execute a command whose name correspond à un object_id."""
    key = _lookup_key(name)
    if not key:
        raise HTTPException(404, "Unknown command / entity")

    typ = _entity_types.get(key)
    client = _ensure_client()

    if typ == "button":
        await _call_api(client, "button_command", key)
        return

    if typ == "switch":
        if not body or "state" not in body:
            raise HTTPException(400, "Switch command requires JSON body {\"state\": true/false}")
        await _call_api(client, "switch_command", key, bool(body["state"]))
        return

    if typ == "number":
        if not body or "value" not in body:
            raise HTTPException(400, "Number command requires JSON body {\"value\": 42}")
        await _call_api(client, "number_command", key, float(body["value"]))
        return

    raise HTTPException(400, f"Unsupported entity type {typ}")


# Handler pour set_sentry_mode qui exige body {"on": bool}
async def _cmd_set_sentry_mode(body: dict[str, Any] | None) -> None:
    if not body or "on" not in body:
        raise HTTPException(400, "set_sentry_mode requiert JSON body {'on': true/false}")
    await _generic_entity_command("sentry_mode", {"state": bool(body["on"])})

_FLEET_COMMANDS["set_sentry_mode"] = _cmd_set_sentry_mode 