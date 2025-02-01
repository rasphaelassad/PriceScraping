from fastapi import APIRouter, HTTPException
from app.schemas.models import PriceRequest
from app.scrapers import get_scraper_for_url, get_supported_stores
import logging
import traceback
from typing import Dict, Any, List
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/supported-stores")
def get_supported_stores_route() -> List[str]:
    """Get a list of supported stores."""
    try:
        return get_supported_stores()
    except Exception as e:
        logger.error(f"Error getting supported stores: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prices")
async def get_prices(request: PriceRequest) -> Dict[str, Any]:
    """
    Get prices for multiple URLs.
    Each URL will be handled by the appropriate store scraper.
    """
    try:
        # Create tasks for each URL
        tasks = []
        errors = []
        
        for url in request.urls:
            try:
                scraper = get_scraper_for_url(str(url))
                tasks.append(scraper.get_price(str(url)))
            except ValueError as e:
                errors.append({"url": str(url), "error": str(e)})
        
        if errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Some URLs are from unsupported stores",
                    "errors": errors,
                    "supported_stores": get_supported_stores()
                }
            )

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        combined_results = {}
        for url, result in zip([str(u) for u in request.urls], results):
            if isinstance(result, Exception):
                combined_results[url] = {
                    "request_status": {
                        "status": "failed",
                        "job_id": None,
                        "start_time": datetime.now(timezone.utc),
                        "elapsed_time_seconds": 0.0,
                        "error_message": str(result)
                    }
                }
            else:
                combined_results[url] = result

        return combined_results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing price request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e)) 