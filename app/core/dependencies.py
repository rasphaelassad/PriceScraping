from app.models.database import SessionLocal
from app.services.cache_service import CacheService
from app.services.db_service import DbService
from app.services.price_service import PriceService
from app.services.request_cache_service import RequestCacheService

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_cache_service(db=next(get_db())):
    """Get cache service instance"""
    return CacheService(db)

def get_db_service(db=next(get_db())):
    """Get database service instance"""
    return DbService(db)

def get_request_cache_service(db=next(get_db())):
    """Get request cache service instance"""
    return RequestCacheService(db)

def get_price_service(db=next(get_db())):
    """Get price service instance"""
    cache_service = get_cache_service(db)
    return PriceService(db, cache_service)
