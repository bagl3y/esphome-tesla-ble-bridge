import asyncio
from typing import Any, Dict

class State:
    def __init__(self) -> None:
        self._values: Dict[str, Any] = {}
        self._entities: Dict[str, Any] = {}
        self._types: Dict[str, str] = {}
        self._oid2key: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self.client = None  # type: ignore
        self.entities = self._entities
        self.entity_types = self._types
        self.oid2key = self._oid2key

    # access helpers
    async def set_value(self, key: str, value: Any) -> None:
        async with self._lock:
            self._values[key] = value

    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            return dict(self._values)

    async def get_value(self, key: str):
        async with self._lock:
            return self._values.get(key)

state = State() 