"""API route handlers."""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import HttpUrl, BaseModel
from app.models import Product
from app.scrapers import get_scraper_for_store, get_supported_stores
import logging
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

class PriceRequest(BaseModel):
    store: str
    store_id: str
    urls: List[HttpUrl]

@router.get("/supported-stores", response_model=List[str])
async def get_supported_stores_route() -> List[str]:
    """Get a list of supported stores."""
    logger.info("Getting list of supported stores")
    stores = get_supported_stores()
    logger.info(f"Found supported stores: {stores}")
    return stores

@router.post("/prices")
async def get_prices(request: PriceRequest) -> Dict[str, Any]:
    """
    Get prices for multiple URLs from a specific store.
    
    Args:
        request: PriceRequest object containing store, store_id and URLs to scrape.
        
    Returns:
        Dictionary mapping URLs to their scraping results.
        
    Raises:
        HTTPException: If the store is not supported.
    """
    logger.info(f"Received request to get prices for store: {request.store}, store_id: {request.store_id}, URLs: {request.urls}")
    
    # Validate store is supported and get scraper
    try:
        scraper = get_scraper_for_store(request.store)
        logger.info(f"Using scraper {scraper.__class__.__name__}")
    except ValueError as e:
        logger.error(f"Store validation error: {str(e)}")
        supported_stores = get_supported_stores()
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(e),
                "supported_stores": supported_stores
            }
        )

    # Convert URLs to strings and fetch prices
    urls = [str(url) for url in request.urls]
    results = await scraper.get_prices(urls, store_id=request.store_id)
    
    # Create response dictionary mapping URLs to their results
    response = dict(zip(urls, results))
    logger.info("Successfully gathered all prices")
    return response

@router.get("/health")
async def get_health() -> Dict[str, str]:
    """Get the health status of the API."""
    return {"status": "OK"}