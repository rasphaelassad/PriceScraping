from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.schemas.request_schemas import PriceRequest, PriceResponse
from app.services.price_service import PriceService
from app.core.scraper_factory import ScraperFactory
import logging
import traceback

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/get-prices", response_model=PriceResponse)
async def get_prices(request: PriceRequest, db: Session = Depends(get_db)):
    """Get prices for the requested URLs."""
    try:
        service = PriceService()
        results = await service.get_prices(request)
        return PriceResponse(results=results)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing price request: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/supported-stores")
def get_supported_stores():
    """Get a list of supported stores."""
    try:
        return {"supported_stores": ScraperFactory.get_supported_stores()}
    except Exception as e:
        logger.error(f"Error getting supported stores: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/raw-scrape")
async def get_raw_html(request: PriceRequest, db: Session = Depends(get_db)):
    """Get raw HTML/JSON response without processing."""
    try:
        service = PriceService()
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