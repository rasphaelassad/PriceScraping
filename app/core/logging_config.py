import logging
import os
from datetime import datetime

def configure_logging():
    """Configure application logging."""
    os.makedirs('logs', exist_ok=True)
    log_filename = f"logs/app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Set log level based on environment variable
    log_level = logging.DEBUG if os.getenv("DEBUG", "").lower() == "true" else logging.INFO

    logging.basicConfig(
        level=log_level,  # Will be DEBUG if DEBUG=true in environment
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_filename)
        ]
    )

    # Set specific loggers to DEBUG level when in debug mode
    if log_level == logging.DEBUG:
        logging.getLogger('app.scrapers').setLevel(logging.DEBUG)
        logging.getLogger('app.api').setLevel(logging.DEBUG)
        logging.getLogger('aiohttp').setLevel(logging.DEBUG)