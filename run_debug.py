import uvicorn
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from datetime import datetime

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging
def setup_logging():
    """Configure detailed logging for debugging"""
    # Generate timestamp for log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/debug_{timestamp}.log'

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler with color formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # File handler with detailed formatting
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # Add handlers to root logger
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Set SQLAlchemy logging to DEBUG
    logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)

    # Log startup message
    root_logger.info('='*80)
    root_logger.info(f'Starting application in DEBUG mode - Log file: {log_file}')
    root_logger.info('='*80)

def main():
    """Run the application in debug mode"""
    # Setup logging first
    setup_logging()

    # Import app after logging is configured
    from app.main import app
    
    # Get logger for this module
    logger = logging.getLogger(__name__)
    
    try:
        # Log environment details
        logger.info('Python version: %s', sys.version)
        logger.info('Working directory: %s', os.getcwd())
        logger.info('Environment variables:')
        for key, value in os.environ.items():
            if 'SECRET' not in key.upper() and 'PASSWORD' not in key.upper():
                logger.info('  %s: %s', key, value)

        # Run the application
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="debug",
            access_log=True
        )
    except Exception as e:
        logger.exception('Fatal error occurred:')
        raise

if __name__ == "__main__":
    main() 