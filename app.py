import uvicorn
from src.config.settings import load as load_settings
from src.interface_http.logging import HealthCheckFilter

if __name__ == "__main__":
    settings = load_settings()
    log_level = settings.log_level.upper()

    # Get the default Uvicorn log config and make a copy
    log_config = uvicorn.config.LOGGING_CONFIG.copy()

    # Override the formatters to include a timestamp
    log_config["formatters"]["default"]["fmt"] = "[%(asctime)s] %(levelname)s: %(message)s"
    log_config["formatters"]["access"]["fmt"] = '[%(asctime)s] %(levelname)s: %(client_addr)s - "%(request_line)s" %(status_code)s'
    
    # Configure the root logger to use our new default formatter
    log_config["loggers"][""] = {
        "handlers": ["default"], 
        "level": log_level,
    }

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=log_config,
    ) 