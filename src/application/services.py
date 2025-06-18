import asyncio
from fastapi import HTTPException
from domain.state import state

async def call_api(method: str, *args):
    c = state.client
    if c is None:
        raise HTTPException(503)
    fn = getattr(c, method)
    if asyncio.iscoroutinefunction(fn):
        await fn(*args)
    else:
        fn(*args)


def ensure_client():
    if state.client is None:
        raise HTTPException(503, "ESPHome client not connected")
    return state.client 