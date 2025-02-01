import logging
import os
from datetime import datetime

def configure_logging():
    """Configure application logging."""
    os.makedirs('logs', exist_ok=True)
    log_filename = f"logs/app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,  # Set to DEBUG for debugging
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_filename)
        ]
    ) 