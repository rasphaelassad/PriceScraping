from pydantic import BaseModel, HttpUrl
from typing import List

class PriceRequest(BaseModel):
    store_name: str
    urls: List[HttpUrl]

class PriceResponse(BaseModel):
    results: dict
    error: str = None 