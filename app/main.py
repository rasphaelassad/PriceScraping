from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router as api_router
from app.core.config import get_settings
import logging
import traceback
import os
from datetime import datetime

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging
log_filename = f"logs/debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename)
    ]
)

# Set logging levels
logging.getLogger('httpx').setLevel(logging.INFO)

# Get root logger
logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info(f"Starting application in DEBUG mode - Log file: {log_filename}")
logger.info("=" * 80)

# Create FastAPI app
app = FastAPI(
    title="Store Price API",
    description="API for scraping product prices from various stores",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler caught: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )

# Health check endpoint
@app.get("/health")
def health_check():
    """Check if the API is healthy."""
    return {"status": "healthy"}