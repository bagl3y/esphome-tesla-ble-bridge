import logging
import math
from fastapi import APIRouter, Body, Query, HTTPException, Request, Depends
from src.domain.state import state_manager, VehicleState
from src.application.services import call_api
from src.config.settings import load as load_settings
from typing import Any, Optional

# Load settings to get configured VINs for validation
settings = load_settings()
configured_vins = {v.vin for v in settings.vehicles if v.vin}

log = logging.getLogger(__name__)

async def validate_vin(vin: str) -> str:
    """Dependency to validate that the VIN is present in the configuration."""
    if vin not in configured_vins:
        raise HTTPException(status_code=404, detail=f"Vehicle with VIN {vin} not configured.")
    return vin

async def get_current_vehicle_state(vin: str = Depends(validate_vin)) -> VehicleState:
    """Dependency to get the state for the current, validated vehicle."""
    return await state_manager.get_vehicle_state(vin)

async def check_client_connected(state: VehicleState = Depends(get_current_vehicle_state)):
    """Dependency to ensure the client for the current vehicle is connected."""
    if state.client is None:
        raise HTTPException(status_code=503, detail="Service Unavailable: ESPHome client not connected")

# The main router for all vehicle-specific fleet routes.
# It validates the VIN and ensures the client is connected for all routes.
router = APIRouter(
    prefix="/api/1/vehicles/{vin}",
    dependencies=[Depends(check_client_connected)],
)

def fleet_resp(payload: Any):
    """Wraps the payload in the standard Tesla Fleet API response format."""
    return {"response": payload}

def attach(app):
    """Attaches this router to the main FastAPI application."""
    app.include_router(router)

def sanitize_float(value: Any) -> Any:
    """Sanitize float values to ensure JSON compatibility."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value

@router.get("/vehicle_data")
async def vehicle_data(
    state: VehicleState = Depends(get_current_vehicle_state),
    endpoints: Optional[str] = Query(None)
):
    snap = await state.snapshot()
    resp = {
        "charge_state": {
            "battery_level": sanitize_float(snap.get("charge_level")),
            "charging_state": snap.get("charging_state"),
            "charge_current_request": sanitize_float(snap.get("charge_current")),
            "charge_limit_soc": sanitize_float(snap.get("charge_limit")),
            "charge_port_door_open": snap.get("charge_flap"),
            "battery_range": sanitize_float(
                snap.get("battery_range")
                or snap.get("range")
                or snap.get("est_range")
                or 0
            ),
        },
        "climate_state": {
            "inside_temp": sanitize_float(snap.get("interior")),
            "outside_temp": sanitize_float(snap.get("exterior")),
            "is_auto_conditioning_on": snap.get("climate"),
        },
    }
    if endpoints:
        wanted = {e.strip() for e in endpoints.split(',')}
        resp = {k: v for k, v in resp.items() if k in wanted}
    return fleet_resp(resp)


@router.get("/body_controller_state")
async def body_state(state: VehicleState = Depends(get_current_vehicle_state)):
    snap = await state.snapshot()
    data = {
        "vehicleLockState": "VEHICLELOCKSTATE_LOCKED" if snap.get("doors") else "VEHICLELOCKSTATE_UNLOCKED",
        "vehicleSleepStatus": "VEHICLE_SLEEP_STATUS_ASLEEP" if snap.get("asleep") else "VEHICLE_SLEEP_STATUS_AWAKE",
        "userPresence": "VEHICLE_USER_PRESENCE_PRESENT" if snap.get("user_presence") else "VEHICLE_USER_PRESENCE_NOT_PRESENT"
    }
    return fleet_resp(data)

async def generic_cmd(vin: str, state: VehicleState, name: str, body: dict | None):
    key = state.oid2key.get(name)
    if not key:
        log.warning("Command failed: key for '%s' not found in oid2key for VIN %s", name, vin)
        raise HTTPException(status_code=404, detail=f"Command '{name}' not found for this vehicle")
    
    typ = state.types.get(key)
    if typ == "button":
        await call_api(vin, "button_command", key)
    elif typ == "switch":
        if not body or "state" not in body:
            raise HTTPException(status_code=400, detail="Missing 'state' in request body for switch command")
        await call_api(vin, "switch_command", key, bool(body["state"]))
    elif typ == "number":
        if not body or "value" not in body:
            raise HTTPException(status_code=400, detail="Missing 'value' in request body for number command")
        await call_api(vin, "number_command", key, float(body["value"]))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported entity type '{typ}' for command")


@router.post("/command/{cmd_name}")
async def run_command(
    vin: str = Depends(validate_vin),
    state: VehicleState = Depends(get_current_vehicle_state),
    cmd_name: str = ...,
    req: Request = ...,
):
    try:
        body = await req.json()
    except Exception:
        body = {}

    # Define the command map inside the function to have access to vin and state
    command_map = {
        "wake_up": lambda b: generic_cmd(vin, state, "wake_up", None),
        "charge_start": lambda b: generic_cmd(vin, state, "charger", {"state": True}),
        "charge_stop": lambda b: generic_cmd(vin, state, "charger", {"state": False}),
        "set_charging_amps": lambda b: generic_cmd(vin, state, "charging_amps", {"value": b.get("charging_amps")}),
        "set_charge_limit": lambda b: generic_cmd(vin, state, "charging_limit", {"value": b.get("percent")}),
        "auto_conditioning_start": lambda b: generic_cmd(vin, state, "climate", {"state": True}),
        "auto_conditioning_stop": lambda b: generic_cmd(vin, state, "climate", {"state": False}),
        "charge_port_door_open": lambda b: generic_cmd(vin, state, "charge_port", {"state": True}),
        "charge_port_door_close": lambda b: generic_cmd(vin, state, "charge_port", {"state": False}),
        "flash_lights": lambda b: generic_cmd(vin, state, "flash_light", None),
        "honk_horn": lambda b: generic_cmd(vin, state, "sound_horn", None),
        "unlock_charge_port": lambda b: generic_cmd(vin, state, "unlock_charge_port", None),
        "set_sentry_mode": lambda b: generic_cmd(vin, state, "sentry_mode", {"state": b.get("on")}),
    }

    # Use the specific command if found, otherwise fall back to the generic handler with the command name
    fn = command_map.get(cmd_name) or (lambda b: generic_cmd(vin, state, cmd_name, b))
    await fn(body)
    return fleet_resp({"result": True})

# These routes are now vehicle-specific and live under the main router.
@router.get("/state/{name}")
async def get_state(name: str, state: VehicleState = Depends(get_current_vehicle_state)):
    val = await state.get(name)
    if val is None:
        # If not found, try to look up via object_id
        if name in state.oid2key:
            key = state.oid2key[name]
            val = await state.get(key)

    if val is None:
        raise HTTPException(status_code=404, detail=f"State for '{name}' not found")

    return {"name": name, "value": val}

@router.get("/entities")
async def list_entities(state: VehicleState = Depends(get_current_vehicle_state)):
    return state.entities