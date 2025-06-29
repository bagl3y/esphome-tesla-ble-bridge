import uvicorn
from src.config.settings import load as load_settings
from src.interface_http.logging import HealthCheckFilter

if __name__ == "__main__":
    settings = load_settings()
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
                "format": '[%(asctime)s] %(levelname)s: %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
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
            },
        },
        "loggers": {
            # Root logger for application code
            "": {"handlers": ["default"], "level": log_level, "propagate": False},
            # Uvicorn's error logger
            "uvicorn.error": {"level": log_level, "handlers": ["default"], "propagate": False},
            # Uvicorn's access logger
            "uvicorn.access": {"handlers": ["access"], "level": log_level, "propagate": False},
        },
    }

    # Filter out /health logs if log level is INFO
    if log_level == "INFO":
        log_config["filters"] = {
            "health_check_filter": {"()": HealthCheckFilter}
        }
        log_config["loggers"]["uvicorn.access"]["filters"] = ["health_check_filter"]

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=log_config,
    ) 