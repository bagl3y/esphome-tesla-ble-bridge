from fastapi import FastAPI, Depends
from src.application.services import ensure_client
from src.domain.state import state_manager, VehicleState


app = FastAPI()

@app.get("/health/live")
def liveness_probe():
    """Returns 200 OK to indicate the service is running."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness_probe(vin: str = Depends(ensure_client)):
    """Returns 200 OK if the service is connected to ESPHome."""
    return {"status": "ready"}


@app.get("/")
def read_root():
    return {"Hello": "World"} 