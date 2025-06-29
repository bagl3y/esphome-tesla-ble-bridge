import asyncio, logging
import logging.config
from src.config.settings import load as load_settings
from src.infrastructure.mqtt_client import init as mqtt_init
from src.infrastructure.esp_client import run as esp_run
from src.interface_http.http_app import app
from src.interface_http.fleet_routes import attach as attach_routes
from src.interface_http.logging import HealthCheckFilter

settings = load_settings()

# Setup logging configuration
log_level = settings.log_level.upper()
log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '[%(asctime)s] %(levelname)s: %(client_addr)s - "%(request_line)s" %(status_code)s',
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "use_colors": False,
        },
    },
    "filters": {
        "health_check_filter": {
            "()": HealthCheckFilter,
            "log_level": log_level,
        }
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["health_check_filter"],
        },
    },
    "loggers": {
        "": {"handlers": ["default"], "level": log_level, "propagate": False},
        "uvicorn": {"handlers": ["default"], "level": log_level, "propagate": False},
        "uvicorn.error": {"level": log_level, "handlers": ["default"], "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": "DEBUG", "propagate": False},
        "src": {"handlers": ["default"], "level": log_level, "propagate": False},
    },
}

logging.config.dictConfig(log_config)

esp_tasks = []

logging.info("Bridge starting with log_level=%s", settings.log_level)

attach_routes(app)

mqtt_cli, publish = mqtt_init(settings)


@app.on_event("startup")
async def startup():
    # Create a connection task for each configured vehicle
    for vehicle in settings.vehicles:
        if not vehicle.vin:
            logging.warning("Skipping vehicle without VIN in config: %s", vehicle.host)
            continue
        logging.info("Starting connection handler for vehicle %s (%s)", vehicle.vin, vehicle.host)
        task = asyncio.create_task(esp_run(vehicle, publish))
        esp_tasks.append(task)


@app.on_event("shutdown")
async def shutdown():
    # Cleanly cancel all running ESPHome connection tasks
    logging.info("Cancelling ESPHome connection tasks...")
    for task in esp_tasks:
        task.cancel()

    if esp_tasks:
        await asyncio.gather(*esp_tasks, return_exceptions=True)
        logging.info("All ESPHome tasks cancelled.")

    if mqtt_cli:
        logging.info("Disconnecting MQTT client...")
        mqtt_cli.loop_stop()
        mqtt_cli.disconnect()
        logging.info("MQTT client disconnected.") 