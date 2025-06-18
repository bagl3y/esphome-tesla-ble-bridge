import asyncio
from typing import Any, Dict

class State:
    def __init__(self):
        self.values: Dict[str, Any] = {}
        self.entities: Dict[str, Any] = {}
        self.types: Dict[str, str] = {}
        self.oid2key: Dict[str, str] = {}
        self.client = None  # ESP client
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any):
        async with self._lock:
            self.values[key] = value

    async def get(self, key: str):
        async with self._lock:
            return self.values.get(key)

    async def snapshot(self):
        async with self._lock:
            return dict(self.values)

state = State() 