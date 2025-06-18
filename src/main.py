import asyncio, logging
from bridge import config, mqtt, esp, http_api, fleet_api

settings = config.load_settings()
logging.basicConfig(level=settings.log_level)

app = http_api.app
fleet_api.attach(app)

mqtt_client, publish = mqtt.init(settings)

@app.on_event("startup")
async def _startup():
    asyncio.create_task(esp.run(settings, publish))

@app.on_event("shutdown")
async def _shutdown():
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect() 