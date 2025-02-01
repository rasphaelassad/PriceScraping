from fastapi import APIRouter, HTTPException
from app.schemas.models import PriceRequest
from app.scrapers import get_scraper_for_url, get_supported_stores
import logging
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/supported-stores")
def get_supported_stores_route():
    """Get a list of supported stores."""
    return get_supported_stores()

@router.post("/prices")
async def get_prices(request: PriceRequest):
    """Get prices for multiple URLs."""
    tasks = []
    unsupported_stores = []

    for url in request.urls:
        try:
            scraper = get_scraper_for_url(str(url))
            tasks.append(scraper.get_price(str(url)))
        except ValueError:
            unsupported_stores.append(str(url))

    if unsupported_stores:
        logger.warning(f"Unsupported stores: {unsupported_stores}")
        raise HTTPException(status_code=400, detail="One or more URLs are from unsupported stores.")

    results = await asyncio.gather(*tasks)
    return dict(zip([str(url) for url in request.urls], results)) 