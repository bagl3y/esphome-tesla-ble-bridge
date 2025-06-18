import asyncio
from fastapi import HTTPException
from .state import state

async def call_api(method: str, *args):
    client = state.client
    if client is None:
        raise HTTPException(503, "ESPHome client not connected")
    func = getattr(client, method)
    if asyncio.iscoroutinefunction(func):
        await func(*args)
    else:
        func(*args)


def ensure_client():
    if state.client is None:
        raise HTTPException(503, "ESPHome client not connected")
    return state.client 