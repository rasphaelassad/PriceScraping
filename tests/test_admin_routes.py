import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
from app.main import app
from app.models.database import Base, Product, RequestCache, get_db
from app.schemas.request_schemas import ProductInfo
import os

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    """Setup a fresh test database before each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def sample_data():
    """Insert sample data into the test database."""
    db = TestingSessionLocal()
    try:
        # Create sample products
        products = [
            Product(
                store="store1",
                url="http://example.com/product1",
                name="Product 1",
                price=10.99,
                price_string="$10.99",
                timestamp=datetime.now(timezone.utc)
            ),
            Product(
                store="store2",
                url="http://example.com/product2",
                name="Product 2",
                price=20.99,
                price_string="$20.99",
                timestamp=datetime.now(timezone.utc)
            )
        ]
        db.add_all(products)

        # Create sample requests
        requests = [
            RequestCache(
                store="store1",
                url="http://example.com/product1",
                job_id="job1",
                status="completed",
                start_time=datetime.now(timezone.utc),
                update_time=datetime.now(timezone.utc),
                price_found=True
            ),
            RequestCache(
                store="store2",
                url="http://example.com/product2",
                job_id="job2",
                status="pending",
                start_time=datetime.now(timezone.utc),
                update_time=datetime.now(timezone.utc),
                price_found=False
            ),
            RequestCache(
                store="store3",
                url="http://example.com/product3",
                job_id="job3",
                status="failed",
                start_time=datetime.now(timezone.utc),
                update_time=datetime.now(timezone.utc),
                price_found=False,
                error_message="Test error"
            )
        ]
        db.add_all(requests)
        db.commit()
    finally:
        db.close()

def test_get_tables(sample_data):
    """Test getting list of database tables."""
    response = client.get("/admin/tables")
    assert response.status_code == 200
    assert "products" in response.json()["tables"]
    assert "request_cache" in response.json()["tables"]

def test_get_table_data_products(sample_data):
    """Test getting data from products table."""
    response = client.get("/admin/table/products")
    assert response.status_code == 200
    data = response.json()
    assert len(data["rows"]) == 2
    assert data["table_name"] == "products"
    assert "store" in data["columns"]
    assert "url" in data["columns"]

def test_get_table_data_invalid_table():
    """Test getting data from non-existent table."""
    response = client.get("/admin/table/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_get_stats(sample_data):
    """Test getting database statistics."""
    response = client.get("/admin/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total_products"] == 2
    assert stats["unique_stores"] == 2
    assert stats["active_requests"] == 1  # pending request
    assert stats["completed_requests"] == 1
    assert stats["failed_requests"] == 1
    assert stats["latest_update"] is not None

def test_cleanup_database(sample_data):
    """Test cleaning up stale requests and old products."""
    # Add a stale request and old product
    db = TestingSessionLocal()
    try:
        old_time = datetime.now(timezone.utc) - timedelta(days=31)
        stale_request = RequestCache(
            store="store4",
            url="http://example.com/product4",
            job_id="job4",
            status="pending",
            start_time=old_time,
            update_time=old_time,
            price_found=False
        )
        old_product = Product(
            store="store4",
            url="http://example.com/product4",
            name="Old Product",
            price=30.99,
            price_string="$30.99",
            timestamp=old_time
        )
        db.add(stale_request)
        db.add(old_product)
        db.commit()

        response = client.get("/admin/cleanup")
        assert response.status_code == 200
        result = response.json()
        assert result["stale_requests_deleted"] > 0
        assert result["old_products_deleted"] > 0
    finally:
        db.close()

def test_get_active_requests(sample_data):
    """Test getting active requests."""
    response = client.get("/admin/requests/active")
    assert response.status_code == 200
    requests = response.json()
    assert len(requests) == 1
    assert requests[0]["status"] == "pending"
    assert requests[0]["store"] == "store2"
    assert "elapsed_time" in requests[0]

def test_get_failed_requests(sample_data):
    """Test getting failed requests."""
    response = client.get("/admin/requests/failed")
    assert response.status_code == 200
    requests = response.json()
    assert len(requests) == 1
    assert requests[0]["status"] == "failed"
    assert requests[0]["store"] == "store3"
    assert requests[0]["error_message"] == "Test error"

def test_delete_request(sample_data):
    """Test deleting a specific request."""
    # First get a request ID
    db = TestingSessionLocal()
    try:
        request = db.query(RequestCache).first()
        request_id = request.id
        db.close()

        # Delete the request
        response = client.delete(f"/admin/requests/{request_id}")
        assert response.status_code == 200
        assert response.json()["message"] == "Request deleted successfully"

        # Verify request is deleted
        db = TestingSessionLocal()
        deleted_request = db.query(RequestCache).filter(RequestCache.id == request_id).first()
        assert deleted_request is None
    finally:
        db.close()

def test_delete_nonexistent_request():
    """Test deleting a non-existent request."""
    response = client.delete("/admin/requests/999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_database_error_handling(monkeypatch):
    """Test error handling when database operations fail."""
    def mock_query(*args, **kwargs):
        raise Exception("Database error")

    def mock_get_db():
        raise Exception("Database error")

    # Override the dependency
    app.dependency_overrides[get_db] = mock_get_db

    try:
        # Test error handling in various endpoints
        endpoints = [
            "/admin/tables",
            "/admin/stats",
            "/admin/requests/active",
            "/admin/requests/failed"
        ]

        for endpoint in endpoints:
            try:
                response = client.get(endpoint)
            except Exception as e:
                assert "Database error" in str(e)
    finally:
        # Clean up the override
        app.dependency_overrides.clear() 