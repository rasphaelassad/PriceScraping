"""API route handlers."""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import HttpUrl
from app.models import Product
from app.scrapers import get_scraper_for_url, get_supported_stores
import logging
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/supported-stores", response_model=List[str])
async def get_supported_stores_route() -> List[str]:
    """Get a list of supported stores."""
    print("get_supported_stores_route")
    return get_supported_stores()

@router.post("/prices")
async def get_prices(urls: List[HttpUrl]) -> Dict[str, Any]:
    print("get_prices_route")
    """
    Get prices for multiple URLs.
    
    Args:
        urls: List of product URLs to scrape.
        
    Returns:
        Dictionary mapping URLs to their scraping results.
        
    Raises:
        HTTPException: If any URLs are from unsupported stores.
    """
    tasks = []
    unsupported_urls = []

    for url in urls:
        try:
            scraper = get_scraper_for_url(str(url))
            tasks.append(scraper.get_price(str(url)))
        except ValueError as e:
            unsupported_urls.append({"url": str(url), "error": str(e)})

    if unsupported_urls:
        supported_stores = get_supported_stores()
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Some URLs are from unsupported stores",
                "unsupported_urls": unsupported_urls,
                "supported_stores": supported_stores
            }
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return dict(zip([str(url) for url in urls], results))