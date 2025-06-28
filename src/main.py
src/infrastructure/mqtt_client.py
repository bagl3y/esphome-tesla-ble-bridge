import asyncio, logging
from src.config.settings import load as load_settings
from src.infrastructure.mqtt_client import init as mqtt_init
from src.infrastructure.esp_client import run as esp_run
from src.interface_http.http_app import app
from src.interface_http.fleet_routes import attach as attach_routes

settings = load_settings()

# ... (logging config)

attach_routes(app)

# The publish function now accepts a VIN
mqtt_cli, publish = mqtt_init(settings)

@app.on_event("startup")
async def startup():
    # Create a connection task for each configured vehicle
    for vehicle in settings.vehicles:
        if not vehicle.vin:
            logging.warning("Skipping vehicle without VIN in config: %s", vehicle.host)
            continue
        logging.info("Starting connection handler for vehicle %s", vehicle.vin)
        asyncio.create_task(esp_run(vehicle, publish))

# ... (shutdown handler) 