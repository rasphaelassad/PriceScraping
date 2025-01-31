
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.schemas.request_schemas import PriceRequest
from app.scrapers.store_registry import SUPPORTED_STORES

router = APIRouter(prefix="/api", tags=["stores"])

@router.get("/supported-stores")
def get_supported_stores():
    return {"supported_stores": list(SUPPORTED_STORES.keys())}

@router.post("/get-prices")
async def get_prices(request: PriceRequest, db: Session = Depends(get_db)):
    try:
        store_name = request.store_name.lower()
        if store_name not in SUPPORTED_STORES:
            raise HTTPException(status_code=400, detail=f"Unsupported store: {store_name}")
        
        scraper = SUPPORTED_STORES[store_name]()
        return await scraper.get_prices(request.urls, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
