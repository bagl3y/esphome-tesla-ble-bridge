import asyncio
from typing import Any, Dict, Optional


class VehicleState:
    """Represents the state of a single vehicle."""
    def __init__(self):
        self.values: Dict[str, Any] = {}
        self.entities: Dict[str, Any] = {}
        self.types: Dict[str, str] = {}
        self.oid2key: Dict[str, str] = {}
        self.client: Optional[Any] = None  # aioesphomeapi.APIClient
        self.initialized: bool = False  # Flag to indicate full initialization
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any):
        async with self._lock:
            self.values[key] = value

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            return self.values.get(key)

    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            return dict(self.values)


class StateManager:
    """Manages the state of all configured vehicles."""
    def __init__(self):
        self._states: Dict[str, VehicleState] = {}
        self._lock = asyncio.Lock()

    async def get_vehicle_state(self, vin: str) -> VehicleState:
        # Fast path without lock
        if vin in self._states:
            return self._states[vin]
        
        # Slow path with lock for creation
        async with self._lock:
            if vin not in self._states:
                self._states[vin] = VehicleState()
            return self._states[vin]

# Global instance to be used across the application
state_manager = StateManager() 