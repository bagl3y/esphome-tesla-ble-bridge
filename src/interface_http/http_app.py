from fastapi import FastAPI, HTTPException
from src.config.settings import load as load_settings
from src.domain.state import state_manager

settings = load_settings()
app = FastAPI()


@app.get("/health/live")
def liveness_probe():
    """Returns 200 OK to indicate the service is running."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness_probe():
    """
    Returns 200 OK if at least one vehicle is connected to ESPHome.
    Otherwise, returns 503 Service Unavailable.
    """
    for vehicle in settings.vehicles:
        if not vehicle.vin:
            continue
        # This is an internal check, so we don't need to lock
        if vehicle.vin in state_manager._states and state_manager._states[vehicle.vin].client is not None:
            return {"status": "ready"}

    raise HTTPException(status_code=503, detail="Service Unavailable: No vehicles connected")


@app.get("/")
def read_root():
    return {"Hello": "World"} 