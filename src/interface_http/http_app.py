from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .state import state

app = FastAPI(title="Tesla BLE Bridge", version="0.1.0")


def _lookup_key(oid: str):
    return state.oid2key.get(oid)


@app.get("/state/{name}")
async def get_state(name: str):
    val = await state.get_value(name) or await state.get_value(_lookup_key(name) or "")
    if val is None:
        raise HTTPException(404)
    return {"name": name, "value": val}


@app.get("/entities")
async def list_entities():
    snap = await state.snapshot()
    res = []
    for k, ent in state.entities.items():
        res.append({
            "key": k,
            "name": ent.name,
            "object_id": getattr(ent, "object_id", None),
            "unit": getattr(ent, "unit_of_measurement", None),
            "platform": state.entity_types.get(k),
            "state": snap.get(k)
        })
    return JSONResponse(content=res) 