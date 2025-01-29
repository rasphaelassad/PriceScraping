from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from app.models.database import get_db, Product, PendingRequest
from typing import Dict, Any
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