import uvicorn
import logging.config
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
                "format": "[%(asctime)s] %(levelname)s: %(client_addr)s - \"%(request_line)s\" %(status_code)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
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
            # Root logger for application code
            "": {"handlers": ["default"], "level": log_level, "propagate": False},
            # ALL uvicorn loggers - use our format
            "uvicorn": {"level": log_level, "handlers": ["default"], "propagate": False},
            "uvicorn.error": {"level": log_level, "handlers": ["default"], "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": "DEBUG", "propagate": False},
            # Application logger
            "src": {"handlers": ["default"], "level": log_level, "propagate": False},
        },
    }

    # Apply logging configuration BEFORE starting uvicorn
    logging.config.dictConfig(log_config)

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=log_config,
        # Force uvicorn to not override our logging config
        use_colors=False,
    ) 