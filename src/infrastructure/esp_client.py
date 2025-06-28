import asyncio, logging, aioesphomeapi
from typing import Any, Callable
from src.domain.state import state_manager
from src.config.settings import Vehicle
import contextlib

logger = logging.getLogger(__name__)

ENTITY_MAP = {"battery_level": "soc", "connected": "connected", "charging": "charging"}

async def run(vehicle: Vehicle, publish: Callable[[str, str, str], None]):
    
    # Get the state manager for this specific vehicle
    vehicle_state = await state_manager.get_vehicle_state(vehicle.vin)

    async def state_cb(msg):
        await vehicle_state.set(msg.key, msg.state)
        ent = vehicle_state.entities.get(msg.key)
        if ent and getattr(ent, "object_id", None):
            await vehicle_state.set(ent.object_id, msg.state)
        s = ENTITY_MAP.get(msg.key)
        if s:
            # Pass VIN to publish function
            publish(vehicle.vin, s, str(msg.state))
        logger.debug("State update for %s: %s = %s", vehicle.vin, msg.key, msg.state)

    while True:
        client = None
        try:
            client_kwargs = {}
            if vehicle.encryption_key:
                client_kwargs["noise_psk"] = vehicle.encryption_key
            client = aioesphomeapi.APIClient(
                vehicle.host, vehicle.port, vehicle.password or "", **client_kwargs
            )
            
            await client.connect(login=True)
            # Store client in the vehicle-specific state
            vehicle_state.client = client

            ent_res = await client.list_entities_services()
            ent_list = ent_res[0] if isinstance(ent_res, tuple) else ent_res
            for ent in ent_list:
                vehicle_state.entities[ent.key] = ent
                raw = ent.__class__.__name__
                platform = raw.replace("ListEntities", "").replace("Response", "").lower()
                if platform.endswith("info"):
                    platform = platform[:-4]
                if platform.endswith("sensor") and not platform.endswith("_sensor"):
                    platform = platform[:-6] + "_sensor"
                vehicle_state.types[ent.key] = platform
                if getattr(ent, "object_id", None):
                    vehicle_state.oid2key[ent.object_id] = ent.key
            logger.debug("Entities discovered for %s: %s", vehicle.vin, len(vehicle_state.entities))

            client.subscribe_states(lambda s: asyncio.create_task(state_cb(s)))

            # initial states
            try:
                init_states = await client.get_states()
                for s in init_states:
                    await state_cb(s)
                logger.debug("Initial states for %s cached: %s", vehicle.vin, len(init_states))
            except Exception:
                pass

            try:
                # wait_until_disconnected() is a Future that will complete when the
                # connection is lost.
                async def keepalive():
                    while True:
                        await asyncio.sleep(60)
                        await client.ping()

                await asyncio.gather(client.wait_until_disconnected(), keepalive())
            except AttributeError:
                # fallback for older aioesphomeapi versions
                await asyncio.Future()

        except Exception as e:  # reconnect on any error
            logger.warning("ESP loop error for %s: %s", vehicle.vin, e)
            # Mark the client as disconnected so that HTTP endpoints return 503
            vehicle_state.client = None
            if client:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), 5)
            await asyncio.sleep(5) 