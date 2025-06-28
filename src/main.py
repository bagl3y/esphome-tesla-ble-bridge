import asyncio, logging
from src.config.settings import load as load_settings
from src.infrastructure.mqtt_client import init as mqtt_init
from src.infrastructure.esp_client import run as esp_run
from src.interface_http.http_app import app
from src.interface_http.fleet_routes import attach as attach_routes

settings = load_settings()

# force override logging config so DEBUG messages show even with uvicorn
logging.basicConfig(
    level=settings.log_level.upper(),
    format="[%(asctime)s] %(levelname)s: %(message)s",
    force=True,
)
logging.debug("Bridge starting with log_level=%s", settings.log_level)

attach_routes(app)

mqtt_cli, publish = mqtt_init(settings)

@app.on_event("startup")
async def startup():
    asyncio.create_task(esp_run(settings, publish))

@app.on_event("shutdown")
async def shutdown():
    if mqtt_cli:
        logging.info("Disconnecting MQTT client...")
        mqtt_cli.loop_stop()
        mqtt_cli.disconnect()
        logging.info("MQTT client disconnected.") 