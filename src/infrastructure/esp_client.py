import asyncio, logging, aioesphomeapi
from typing import Any, Callable
from src.domain.state import state
from src.config.settings import Settings
import contextlib

logger = logging.getLogger(__name__)

ENTITY_MAP = {"battery_level": "soc", "connected": "connected", "charging": "charging"}

async def run(settings: Settings, publish: Callable[[str,str],None]):
    veh = settings.vehicles[0]
    
    async def state_cb(msg):
        await state.set(msg.key, msg.state)
        ent = state.entities.get(msg.key)
        if ent and getattr(ent, "object_id", None):
            await state.set(ent.object_id, msg.state)
        s = ENTITY_MAP.get(msg.key)
        if s:
            publish(s, str(msg.state))
        logger.debug("state update %s = %s", msg.key, msg.state)

    while True:
        client = None
        try:
            client_kwargs = {}
            if veh.encryption_key:
                client_kwargs["noise_psk"] = veh.encryption_key
            client = aioesphomeapi.APIClient(
                veh.host, veh.port, veh.password or "", **client_kwargs
            )
            
            await client.connect(login=True)
            state.client = client

            ent_res = await client.list_entities_services()
            ent_list = ent_res[0] if isinstance(ent_res, tuple) else ent_res
            for ent in ent_list:
                state.entities[ent.key] = ent
                raw = ent.__class__.__name__
                platform = raw.replace("ListEntities", "").replace("Response", "").lower()
                if platform.endswith("info"):
                    platform = platform[:-4]
                if platform.endswith("sensor") and not platform.endswith("_sensor"):
                    platform = platform[:-6] + "_sensor"
                state.types[ent.key] = platform
                if getattr(ent, "object_id", None):
                    state.oid2key[ent.object_id] = ent.key
            logger.debug("entities discovered: %s", len(state.entities))

            client.subscribe_states(lambda s: asyncio.create_task(state_cb(s)))

            # initial states
            try:
                init_states = await client.get_states()
                for s in init_states:
                    await state_cb(s)
                logger.debug("initial states cached: %s", len(init_states))
            except Exception:
                pass

            # Liveness check loop. Replaces wait_until_disconnected.
            while client.is_connected:
                await asyncio.sleep(60)
                await client.ping()
            
            logger.warning("ESPHome device disconnected.")

        except Exception as e:  # reconnect on any error
            logger.warning("ESP loop error: %s", e)
            # Mark the client as disconnected so that HTTP endpoints return 503
            state.client = None
            if client:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), 5)
            await asyncio.sleep(5) 