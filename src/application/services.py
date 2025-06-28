import asyncio
from fastapi import HTTPException
from src.domain.state import state_manager
from aioesphomeapi.core import APIConnectionError
from typing import Any

RECONNECT_TIMEOUT = 10  # seconds


async def _wait_for_reconnect(vin: str):
    # wait for client to be available
    for i in range(10):
        vehicle_state = await state_manager.get_vehicle_state(vin)
        if vehicle_state.client:
            return
        await asyncio.sleep(1)


async def call_api(vin: str, method: str, *args):
    vehicle_state = await state_manager.get_vehicle_state(vin)
    if not vehicle_state.client:
        await _wait_for_reconnect(vin)
        if not vehicle_state.client:
            raise HTTPException(status_code=503, detail="Service Unavailable")
    api = getattr(vehicle_state.client, method)
    return await api(*args)


async def ensure_client(vin: str):
    vehicle_state = await state_manager.get_vehicle_state(vin)
    if vehicle_state.client is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return vehicle_state.client 