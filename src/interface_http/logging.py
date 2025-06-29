import logging
from typing import Any

class HealthCheckFilter(logging.Filter):
    """
    A custom logging filter that only shows health check endpoint logs
    when the configured log level is DEBUG or lower, otherwise filters them out.
    """
    def __init__(self, log_level: str = "INFO"):
        super().__init__()
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if the log record is for a health check endpoint.
        # Uvicorn access logs have a specific structure in record.args.
        # Example: ('127.0.0.1:12345', 'GET', '/health/live', '1.1', 200)
        if len(record.args) >= 3 and isinstance(record.args[2], str):
            path = record.args[2]
            if path.startswith("/health"):
                # Only show health check logs if the configured level is DEBUG or lower
                return self.log_level <= logging.DEBUG
        return True 