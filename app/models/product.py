"""Product data model."""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Product:
    """Product information returned by scrapers."""
    store: str
    url: str
    name: str
    price: Optional[float] = None
    price_string: Optional[str] = None
    store_id: Optional[str] = None
    store_address: Optional[str] = None
    store_zip: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now() 