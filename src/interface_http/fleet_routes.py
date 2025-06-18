from fastapi import APIRouter, Body, Query, HTTPException
from domain.state import state
from application.services import call_api
from typing import Any, Optional

router = APIRouter(prefix="/api/1/vehicles/{vin}")

# helper

def fleet_resp(payload: Any):
    return {"response": payload}


def validate_vin(vin: str):
    cfg_vin = (state.entities and next(iter(state.entities.values()), None))


@router.get("/vehicle_data")
async def vehicle_data(vin: str, endpoints: Optional[str] = Query(None)):
    snap = await state.snapshot()
    resp = {
        "charge_state": {
            "battery_level": snap.get("battery_level"),
            "charging_state": "Charging" if snap.get("charging") else "Stopped",
            "charge_current_request": snap.get("charging_amps"),
            "charge_limit_soc": snap.get("charging_limit"),
        },
        "climate_state": {
            "inside_temp": snap.get("inside_temp"),
            "outside_temp": snap.get("outside_temp"),
        },
    }
    if endpoints:
        wanted = {e.strip() for e in endpoints.split(',')}
        resp = {k: v for k, v in resp.items() if k in wanted}
    return fleet_resp(resp)


@router.get("/body_controller_state")
async def body_state(vin: str):
    snap = await state.snapshot()
    data = {
        "vehicleLockState": "VEHICLELOCKSTATE_LOCKED" if snap.get("doors") else "VEHICLELOCKSTATE_UNLOCKED",
        "vehicleSleepStatus": "VEHICLE_SLEEP_STATUS_ASLEEP" if snap.get("asleep") else "VEHICLE_SLEEP_STATUS_AWAKE",
        "userPresence": "VEHICLE_USER_PRESENCE_PRESENT" if snap.get("user_presence") else "VEHICLE_USER_PRESENCE_NOT_PRESENT"
    }
    return fleet_resp(data)


# ---------------- commands -----------------

async def generic_cmd(name:str, body:dict|None):
    key = state.oid2key.get(name)
    if not key:
        raise HTTPException(404)
    typ = state.types.get(key)
    if typ == "button":
        await call_api("button_command", key)
    elif typ == "switch":
        if not body or "state" not in body:
            raise HTTPException(400)
        await call_api("switch_command", key, bool(body["state"]))
    elif typ == "number":
        if not body or "value" not in body:
            raise HTTPException(400)
        await call_api("number_command", key, float(body["value"]))
    else:
        raise HTTPException(400)


COMMAND_MAP = {
    "wake_up": lambda _: generic_cmd("wake_up", None),
    "charge_start": lambda _: generic_cmd("charger", {"state": True}),
    "charge_stop": lambda _: generic_cmd("charger", {"state": False}),
    "set_charging_amps": lambda body: generic_cmd("charging_amps", {"value": body["charging_amps"]}),
    "set_charge_limit": lambda body: generic_cmd("charging_limit", {"value": body.get("percent")}),
    "auto_conditioning_start": lambda _: generic_cmd("climate", {"state": True}),
    "auto_conditioning_stop": lambda _: generic_cmd("climate", {"state": False}),
    "charge_port_door_open": lambda _: generic_cmd("charge_port", {"state": True}),
    "charge_port_door_close": lambda _: generic_cmd("charge_port", {"state": False}),
    "flash_lights": lambda _: generic_cmd("flash_light", None),
    "honk_horn": lambda _: generic_cmd("sound_horn", None),
    "unlock_charge_port": lambda _: generic_cmd("unlock_charge_port", None),
    "set_sentry_mode": lambda body: generic_cmd("sentry_mode", {"state": body["on"]}),
}


@router.post("/command/{cmd}")
async def run_command(vin: str, cmd: str, wait: bool = Query(False), body: Optional[dict[str, Any]] = Body(None)):
    fn = COMMAND_MAP.get(cmd) or (lambda b: generic_cmd(cmd, b))
    await fn(body or {})
    return fleet_resp({"result": True})


def attach(app):
    app.include_router(router) 