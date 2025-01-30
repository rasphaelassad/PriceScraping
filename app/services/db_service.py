from sqlalchemy.orm import Session
from sqlalchemy import inspect
from typing import Dict, List, Any
from app.models.database import Product, PendingRequest, RequestCache
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class DbService:
    def __init__(self, db: Session):
        self.db = db

    def get_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """Get all data from a specified database table"""
        table_map = {
            'product': Product,
            'pending_request': PendingRequest,
            'request_cache': RequestCache
        }
        
        if table_name not in table_map:
            raise ValueError(f"Invalid table name. Supported tables: {list(table_map.keys())}")
        
        model = table_map[table_name]
        results = []
        
        for row in self.db.query(model).all():
            row_dict = {}
            for column in inspect(model).columns:
                value = getattr(row, column.name)
                row_dict[column.name] = str(value) if value is not None else None
            results.append(row_dict)
        
        return results

    def get_tables(self) -> Dict[str, List[str]]:
        """Get all tables in the database and their structure"""
        tables = {}
        inspector = inspect(self.db.bind)
        
        for table_name in inspector.get_table_names():
            columns = []
            for column in inspector.get_columns(table_name):
                column_info = f"{column['name']} ({column['type']})"
                if column.get('primary_key', False):
                    column_info += " PRIMARY KEY"
                if not column.get('nullable', True):
                    column_info += " NOT NULL"
                columns.append(column_info)
            tables[table_name] = columns
        
        return tables
