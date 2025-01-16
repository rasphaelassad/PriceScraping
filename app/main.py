from fastapi import FastAPI, HTTPException
from .schemas.request_schemas import PriceRequest, PriceResponse
from .scrapers.walmart_scraper import WalmartScraper
from .scrapers.albertsons_scraper import AlbertsonsScraper

app = FastAPI(title="Store Price API")

SUPPORTED_STORES = {
    "walmart": WalmartScraper,
    "albertsons": AlbertsonsScraper
}

@app.post("/get-prices", response_model=PriceResponse)
async def get_prices(request: PriceRequest):
    store_name = request.store_name.lower()
    
    if store_name not in SUPPORTED_STORES:
        raise HTTPException(
            status_code=400,
            detail=f"Store '{store_name}' not supported. Supported stores: {', '.join(SUPPORTED_STORES.keys())}"
        )
    
    scraper = SUPPORTED_STORES[store_name]()
    
    try:
        results = await scraper.get_prices(request.urls)
        return PriceResponse(results=results)
    except Exception as e:
        return PriceResponse(results={}, error=str(e))

@app.get("/supported-stores")
async def get_supported_stores():
    return {"supported_stores": list(SUPPORTED_STORES.keys())} 