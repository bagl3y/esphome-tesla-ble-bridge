import asyncio, logging, aioesphomeapi
from typing import Any, Callable
from .state import state
from .config import Settings
import contextlib

logger = logging.getLogger(__name__)

ENTITY_MAP = {"battery_level": "soc", "connected": "connected", "charging": "charging"}

async def run(settings: Settings, publish: Callable[[str,str],None]):
    veh = settings.vehicles[0]
    client_kwargs = {}
    if veh.encryption_key:
        client_kwargs["noise_psk"] = veh.encryption_key

    client = aioesphomeapi.APIClient(veh.host, veh.port, veh.password or "", **client_kwargs)

    async def state_cb(msg):
        await state.set(msg.key, msg.state)
        simple = ENTITY_MAP.get(msg.key)
        if simple:
            publish(simple, str(msg.state))

    while True:
        try:
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
                state.entity_types[ent.key] = platform
                if getattr(ent, "object_id", None):
                    state.oid2key[ent.object_id] = ent.key

            client.subscribe_states(lambda s: asyncio.create_task(state_cb(s)))
            try:
                await client.wait_until_disconnected()
            except AttributeError:
                await asyncio.Future()
        except Exception as e:  # reconnect on any error
            logger.warning("ESP loop error: %s", e)
            with contextlib.suppress(Exception):
                await client.disconnect()
            await asyncio.sleep(5) 