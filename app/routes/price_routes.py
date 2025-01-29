from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.schemas.request_schemas import PriceRequest, PriceResponse, UrlResult, RequestStatus
from app.services.price_service import PriceService
from app.core.scraper_factory import ScraperFactory
import logging
import traceback
from typing import Dict, List
from pydantic import HttpUrl

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

@router.get("/prices")
@router.post("/prices")
async def get_prices(
    request: PriceRequest = None,
    store: str = None,
    url: HttpUrl = None,
    db: Session = Depends(get_db)
):
    """Get prices for the requested URLs."""
    try:
        service = PriceService()
        
        # Handle both GET and POST requests
        if request is None and store is not None and url is not None:
            # GET request
            request = PriceRequest(store_name=store, urls=[url])
        elif request is None:
            raise HTTPException(status_code=400, detail="Missing required parameters")
        
        # Validate store name before proceeding
        store_name = request.store_name.lower()
        if store_name not in ScraperFactory.get_supported_stores():
            raise HTTPException(status_code=400, detail=f"Invalid store: {store_name}")
            
        results = await service.get_prices(request)
        
        # For GET requests, return single URL result
        if store is not None and url is not None:
            result = results.get(str(url), {})
            return {
                "request_status": result.request_status,
                "result": result.result
            }
            
        # For POST requests, return all results
        if len(request.urls) == 1:
            # Single URL request
            result = results.get(str(request.urls[0]), {})
            return {
                "request_status": result.request_status,
                "result": result.result
            }
        else:
            # Multiple URL request
            return {
                url: {
                    "request_status": result.request_status,
                    "result": result.result
                }
                for url, result in results.items()
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing price request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/raw-scrape")
@router.post("/raw-content")
async def get_raw_html(
    request: PriceRequest = None,
    store: str = None,
    url: HttpUrl = None,
    db: Session = Depends(get_db)
):
    """Get raw HTML/JSON response without processing."""
    try:
        service = PriceService()
        
        # Handle both GET and POST requests
        if request is None and store is not None and url is not None:
            # GET request
            request = PriceRequest(store_name=store, urls=[url])
        elif request is None:
            raise HTTPException(status_code=400, detail="Missing required parameters")
            
        try:
            # Get scraper instance to validate store
            ScraperFactory.get_scraper(request.store_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
            
        return await service.get_raw_content(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting raw content: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"} 