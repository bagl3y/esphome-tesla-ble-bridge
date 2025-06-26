import asyncio
from fastapi import HTTPException
from src.domain.state import state
from aioesphomeapi.core import APIConnectionError

RECONNECT_TIMEOUT = 10  # seconds


async def _wait_for_reconnect(timeout: float = RECONNECT_TIMEOUT, interval: float = 0.5):
    """Wait until state.client is available again or raise TimeoutError."""
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if state.client is not None:
            return state.client
        await asyncio.sleep(interval)
    raise asyncio.TimeoutError()


async def call_api(method: str, *args):
    c = state.client
    if c is None:
        try:
            c = await _wait_for_reconnect()
        except asyncio.TimeoutError:
            raise HTTPException(503)

    fn = getattr(c, method)
    try:
        if asyncio.iscoroutinefunction(fn):
            await fn(*args)
        else:
            fn(*args)
    except APIConnectionError:
        # Connection lost during call ⇒ wait for reconnect and retry
        state.client = None
        try:
            c = await _wait_for_reconnect()
            fn = getattr(c, method)
            if asyncio.iscoroutinefunction(fn):
                await fn(*args)
            else:
                fn(*args)
        except asyncio.TimeoutError:
            raise HTTPException(503)


def ensure_client():
    if state.client is None:
        raise HTTPException(503, "ESPHome client not connected")
    return state.client 