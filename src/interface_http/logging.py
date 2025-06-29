import logging
from typing import Any

class HealthCheckFilter(logging.Filter):
    """
    A custom logging filter that prevents logs from health check endpoints
    from being processed if they are at INFO level.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if the log record is for a health check endpoint.
        # Uvicorn access logs have a specific structure in record.args.
        # Example: ('127.0.0.1:12345', 'GET', '/health/live', '1.1', 200)
        if len(record.args) >= 3 and isinstance(record.args[2], str):
            path = record.args[2]
            if path.startswith("/health"):
                # Returning False stops the log record from being processed.
                return False
        return True 