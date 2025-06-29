import uvicorn
import logging
from src.config.settings import load as load_settings
from src.interface_http.logging import HealthCheckFilter

if __name__ == "__main__":
    settings = load_settings()
    log_level = settings.log_level.upper()

    # Get the default Uvicorn log config
    log_config = uvicorn.config.LOGGING_CONFIG

    # Override the formatters to include a timestamp
    log_config["formatters"]["default"]["fmt"] = "[%(asctime)s] %(levelname)s: %(message)s"
    log_config["formatters"]["access"]["fmt"] = '[%(asctime)s] %(levelname)s: %(client_addr)s - "%(request_line)s" %(status_code)s'

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
        log_level=log_level.lower(),
    ) 