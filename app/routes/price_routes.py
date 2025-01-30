from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.schemas.request_schemas import PriceRequest, PriceResponse, ProductInfo
from app.core.dependencies import get_db, get_price_service, get_request_cache_service
from app.core.scraper_config import SUPPORTED_STORES
from app.core.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/prices", tags=["prices"])

@router.post("/", response_model=PriceResponse)
async def get_prices(
    request: PriceRequest,
    price_service=Depends(get_price_service),
    request_cache_service=Depends(get_request_cache_service),
    db: Session = Depends(get_db)
):
    """
    Get prices for products from various stores
    """
    try:
        logger.info(f"Processing price request for store: {request.store} with {len(request.urls)} URLs")
        request_cache_service.cleanup_stale_entries()
        return await price_service.get_prices(request)
    except Exception as e:
        logger.error(f"Error processing price request: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stores")
def get_supported_stores():
    """
    Get list of supported stores
    """
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@router.get("/raw")
async def get_raw_html(
    request: PriceRequest,
    price_service=Depends(get_price_service),
    db: Session = Depends(get_db)
):
    """
    Get raw HTML/JSON response without processing
    """
    try:
        logger.info(f"Getting raw HTML for store: {request.store}")
        return await price_service.get_raw_html(request)
    except Exception as e:
        logger.error(f"Error getting raw HTML: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
