from fastapi import APIRouter, HTTPException
from app.schemas.request_schemas import PriceRequest
from app.services.price_service import PriceService
from app.core.scraper_factory import ScraperFactory
import logging
import traceback
from typing import Dict, Any, List

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/supported-stores")
def get_supported_stores() -> List[str]:
    """Get a list of supported stores."""
    try:
        return ScraperFactory.get_supported_stores()
    except Exception as e:
        logger.error(f"Error getting supported stores: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prices")
async def get_prices(request: PriceRequest) -> Dict[str, Any]:
    """
    Get prices for multiple URLs.
    The store will be automatically identified from each URL.
    """
    try:
        service = PriceService()
        return await service.get_prices(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing price request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/raw-content")
async def get_raw_content(request: PriceRequest):
    """
    Get raw HTML/JSON response without processing.
    
    POST request with multiple URLs in request body
    """
    try:
        service = PriceService()
            
        try:
            # Get scraper instance to validate store
            ScraperFactory.get_scraper(request.store_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
            
        result = await service.get_raw_content(request)
        
        # For single URL requests, return just the content
        if len(request.urls) == 1:
            url_result = result.get(str(request.urls[0]), {})
            return {"html": url_result.get("content")}
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting raw content: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e)) 