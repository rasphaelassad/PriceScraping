import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Configure logging format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
FILE_HANDLER_FORMAT = logging.Formatter(LOG_FORMAT)

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with both console and file handlers
    """
    logger = logging.getLogger(name)
    
    # Only add handlers if the logger doesn't have any
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(FILE_HANDLER_FORMAT)
        logger.addHandler(console_handler)

        # File handler
        file_handler = RotatingFileHandler(
            logs_dir / "app.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(FILE_HANDLER_FORMAT)
        logger.addHandler(file_handler)

    return logger
