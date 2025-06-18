import asyncio, logging
from config.settings import load as load_settings
from infrastructure.mqtt_client import init as mqtt_init
from infrastructure.esp_client import run as esp_run
from interface_http.http_app import app
from interface_http.fleet_routes import attach as attach_routes

settings = load_settings()
logging.basicConfig(level=settings.log_level)

attach_routes(app)

mqtt_cli, publish = mqtt_init(settings)

@app.on_event("startup")
async def startup():
    asyncio.create_task(esp_run(settings, publish))

@app.on_event("shutdown")
async def shutdown():
    if mqtt_cli:
        mqtt_cli.loop_stop()
        mqtt_cli.disconnect() 