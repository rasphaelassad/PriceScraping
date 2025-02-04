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
    logger.info("Getting list of supported stores")
    stores = get_supported_stores()
    logger.info(f"Found supported stores: {stores}")
    return stores

@router.post("/prices")
async def get_prices(urls: List[HttpUrl]) -> Dict[str, Any]:
    """
    Get prices for multiple URLs.
    
    Args:
        urls: List of product URLs to scrape.
        
    Returns:
        Dictionary mapping URLs to their scraping results.
        
    Raises:
        HTTPException: If any URLs are from unsupported stores.
    """
    logger.info(f"Received request to get prices for URLs: {urls}")
    tasks = []
    unsupported_urls = []

    for url in urls:
        try:
            logger.info(f"Attempting to get scraper for URL: {url}")
            scraper = get_scraper_for_url(str(url))
            logger.info(f"Found scraper {scraper.__class__.__name__} for URL: {url}")
            tasks.append(scraper.get_price(str(url)))
        except ValueError as e:
            logger.error(f"Error getting scraper for URL {url}: {str(e)}")
            unsupported_urls.append({"url": str(url), "error": str(e)})

    if unsupported_urls:
        supported_stores = get_supported_stores()
        logger.error(f"Found unsupported URLs: {unsupported_urls}")
        logger.info(f"Supported stores are: {supported_stores}")
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Some URLs are from unsupported stores",
                "unsupported_urls": unsupported_urls,
                "supported_stores": supported_stores
            }
        )

    logger.info(f"Starting price fetching for {len(tasks)} URLs")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    response = dict(zip([str(url) for url in urls], results))
    logger.info("Successfully gathered all prices")
    return response

@router.post("/raw-content")
async def get_raw_content(urls: List[HttpUrl]) -> Dict[str, Any]:
    """
    Get raw HTML content for multiple URLs.
    
    Args:
        urls: List of product URLs to scrape.
        
    Returns:
        Dictionary mapping URLs to their raw HTML content and metadata.
        
    Raises:
        HTTPException: If any URLs are from unsupported stores.
    """
    logger.info(f"Received request to get raw content for URLs: {urls}")
    tasks = []
    unsupported_urls = []

    for url in urls:
        try:
            logger.info(f"Attempting to get scraper for URL: {url}")
            scraper = get_scraper_for_url(str(url))
            logger.info(f"Found scraper {scraper.__class__.__name__} for URL: {url}")
            tasks.append(scraper.get_raw_content(str(url)))
        except ValueError as e:
            logger.error(f"Error getting scraper for URL {url}: {str(e)}")
            unsupported_urls.append({"url": str(url), "error": str(e)})

    if unsupported_urls:
        supported_stores = get_supported_stores()
        logger.error(f"Found unsupported URLs: {unsupported_urls}")
        logger.info(f"Supported stores are: {supported_stores}")
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Some URLs are from unsupported stores",
                "unsupported_urls": unsupported_urls,
                "supported_stores": supported_stores
            }
        )

    logger.info(f"Starting raw content fetching for {len(tasks)} URLs")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    response = dict(zip([str(url) for url in urls], results))
    logger.info("Successfully gathered all raw content")
    return response

@router.get("/health")
async def get_health() -> Dict[str, str]:
    """Get the health status of the API."""
    return {"status": "OK"}