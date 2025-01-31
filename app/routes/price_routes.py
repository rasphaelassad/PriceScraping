from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.schemas.request_schemas import PriceRequest, PriceResponse, UrlResult, RequestStatus
from app.services.price_service import PriceService
from app.core.scraper_factory import ScraperFactory
import logging
import traceback
from typing import Dict, List, Any
from pydantic import HttpUrl
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/supported-stores")
def get_supported_stores():
    """Get a list of supported stores."""
    try:
        return ScraperFactory.get_supported_stores()
    except Exception as e:
        logger.error(f"Error getting supported stores: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prices")
async def get_prices(request: PriceRequest) -> Dict[str, Any]:
    """Get prices for the requested URLs."""
    try:
        service = PriceService()
        result = await service.get_prices(request)
        
        # Ensure each URL result has the correct structure
        formatted_result = {}
        for url, data in result.items():
            if isinstance(data, dict) and "request_status" in data:
                # Already in correct format
                formatted_result[url] = data
            else:
                # Format the result to include request_status
                formatted_result[url] = {
                    "request_status": {
                        "status": "completed" if data else "failed",
                        "job_id": str(uuid.uuid4()),
                        "start_time": datetime.now(timezone.utc),
                        "elapsed_time_seconds": 0.0,
                        "price_found": bool(data),
                        "details": "Retrieved from cache" if data else "Failed to get price"
                    },
                    "result": data
                }
        
        return formatted_result
        
    except Exception as e:
        logger.error(f"Error processing price request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/raw-content")
async def get_raw_content(request: PriceRequest,db: Session = Depends(get_db)):
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