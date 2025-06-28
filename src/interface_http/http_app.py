from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from src.domain.state import state
from src.application.services import ensure_client

app = FastAPI(title="Tesla BLE Bridge", version="0.1.0")


def _lookup_key(oid: str):
    return state.oid2key.get(oid)


@app.get("/health/live")
def liveness_probe():
    """Returns 200 OK to indicate the service is running."""
    return {"status": "ok"}


@app.get("/health/ready", dependencies=[Depends(ensure_client)])
def readiness_probe():
    """Returns 200 OK if the service is connected to ESPHome."""
    return {"status": "ready"}


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/state/{name}")
async def get_state(name: str):
    val = await state.get(name)
    if val is None:
        # If not found, try to look up via object_id
        key = _lookup_key(name)
        if key:
            val = await state.get(key)

    if val is None:
        raise HTTPException(status_code=404, detail=f"State for '{name}' not found")
        
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
            "platform": state.types.get(k),
            "state": snap.get(k)
        })
    return JSONResponse(content=res) 