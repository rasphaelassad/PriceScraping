from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect, func
from app.models.database import get_db, Product, RequestCache
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/tables")
def get_tables(db: Session = Depends(get_db)):
    """Get all table names in the database."""
    try:
        inspector = inspect(db.bind)
        return {"tables": inspector.get_table_names()}
    except Exception as e:
        logger.error(f"Error getting database tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/table/{table_name}")
def get_table_data(table_name: str, db: Session = Depends(get_db)):
    """Get all data from a specific table."""
    try:
        inspector = inspect(db.bind)
        if table_name not in inspector.get_table_names():
            raise HTTPException(status_code=404, detail=f"Table {table_name} not found")

        # Get table columns
        columns = [column['name'] for column in inspector.get_columns(table_name)]
        
        # Execute raw SQL to get all data
        result = db.execute(f"SELECT * FROM {table_name}")
        rows = [dict(zip(columns, row)) for row in result]
        
        return {
            "table_name": table_name,
            "columns": columns,
            "rows": rows
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching data from table {table_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get statistics about the database."""
    try:
        # Get total number of products
        total_products = db.query(func.count(Product.id)).scalar()

        # Get total number of stores
        unique_stores = db.query(func.count(func.distinct(Product.store))).scalar()

        # Get total number of active requests
        active_requests = db.query(RequestCache).filter(
            RequestCache.status.in_(['pending', 'running'])
        ).count()

        # Get total number of completed requests
        completed_requests = db.query(RequestCache).filter(
            RequestCache.status == 'completed'
        ).count()

        # Get total number of failed requests
        failed_requests = db.query(RequestCache).filter(
            RequestCache.status.in_(['failed', 'timeout'])
        ).count()

        # Get latest update time
        latest_update = db.query(func.max(Product.timestamp)).scalar()
        if latest_update:
            latest_update = latest_update.isoformat()

        return {
            "total_products": total_products,
            "unique_stores": unique_stores,
            "active_requests": active_requests,
            "completed_requests": completed_requests,
            "failed_requests": failed_requests,
            "latest_update": latest_update
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cleanup")
def cleanup_database(db: Session = Depends(get_db)):
    """Clean up stale requests and old products."""
    try:
        # Get current time
        now = datetime.now(timezone.utc)

        # Delete stale requests (older than 24 hours)
        stale_requests = db.query(RequestCache).filter(
            RequestCache.status.in_(['pending', 'running']),
            RequestCache.update_time < now - timedelta(hours=24)
        ).delete(synchronize_session=False)

        # Delete old products (keep last 30 days)
        old_products = db.query(Product).filter(
            Product.timestamp < now - timedelta(days=30)
        ).delete(synchronize_session=False)

        db.commit()

        return {
            "stale_requests_deleted": stale_requests,
            "old_products_deleted": old_products
        }
    except Exception as e:
        logger.error(f"Error cleaning up database: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/requests/active")
def get_active_requests(db: Session = Depends(get_db)):
    """Get all active requests."""
    try:
        active_requests = db.query(RequestCache).filter(
            RequestCache.status.in_(['pending', 'running'])
        ).all()

        now = datetime.now(timezone.utc)
        return [{
            "store": req.store,
            "url": req.url,
            "status": req.status,
            "job_id": req.job_id,
            "start_time": req.start_time.isoformat(),
            "update_time": req.update_time.isoformat(),
            "elapsed_time": (now - req.start_time.replace(tzinfo=timezone.utc)).total_seconds(),
            "error_message": req.error_message
        } for req in active_requests]
    except Exception as e:
        logger.error(f"Error getting active requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/requests/failed")
def get_failed_requests(db: Session = Depends(get_db)):
    """Get all failed requests."""
    try:
        failed_requests = db.query(RequestCache).filter(
            RequestCache.status.in_(['failed', 'timeout'])
        ).all()

        return [{
            "store": req.store,
            "url": req.url,
            "status": req.status,
            "job_id": req.job_id,
            "start_time": req.start_time.isoformat(),
            "update_time": req.update_time.isoformat(),
            "elapsed_time": (req.update_time - req.start_time).total_seconds(),
            "error_message": req.error_message
        } for req in failed_requests]
    except Exception as e:
        logger.error(f"Error getting failed requests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/requests/{request_id}")
def delete_request(request_id: int, db: Session = Depends(get_db)):
    """Delete a specific request."""
    try:
        request = db.query(RequestCache).filter(RequestCache.id == request_id).first()
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        db.delete(request)
        db.commit()

        return {"message": "Request deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting request: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) 