from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.services.db_service import DbService
from app.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/db", tags=["database"])

@router.get("/tables")
def get_tables(db: Session = Depends(get_db)):
    """Get all tables in the database and their structure"""
    try:
        db_service = DbService(db)
        return db_service.get_tables()
    except Exception as e:
        logger.error(f"Error getting tables: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/table/{table_name}")
def get_table_data(table_name: str, db: Session = Depends(get_db)):
    """
    Get all data from a specified database table.
    Currently supports: 'product', 'pending_request', and 'request_cache' tables.
    """
    try:
        db_service = DbService(db)
        return db_service.get_table_data(table_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting table data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
