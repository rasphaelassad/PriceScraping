import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.scraper_factory import ScraperFactory
from app.schemas.request_schemas import RequestStatus, ProductInfo
from app.models.database import Base, engine, init_db
from datetime import datetime, timezone
import asyncio
import json
from unittest.mock import AsyncMock, patch
import os

ALBERTSONS_URLS = ["https://www.albertsons.com/shop/product-details.970555.html"]
CHEFSTORE_URLS = ["https://www.chefstore.com/p/usda-choice-beef-chuck-roast-primal-20-lb-avg-wt/46165"]
WALMART_URLS = ["https://www.walmart.com/ip/Great-Value-All-Purpose-Flour-5-lb/10534869"]

class MockScraper:
    async def get_prices(self, urls):
        await asyncio.sleep(0.1)  # Simulate network delay
        results = {}
        for url in urls:
            product_info = ProductInfo(
                name="Test Product",  # This maps to the non-nullable name field
                price=9.99,
                price_string="$9.99",
                price_per_unit=None,
                price_per_unit_string=None,
                store_id=None,
                store_address=None,
                store_zip=None,
                brand="Test Brand",
                sku=None,
                category="Test Category",
                timestamp=datetime.now(timezone.utc)
            )
            results[url] = product_info
        return results

    async def get_raw_content(self, urls):
        await asyncio.sleep(0.1)  # Simulate network delay
        return {"html": "<html>Test content</html>"}

@pytest.fixture(scope="function")
def setup_database():
    # Set testing flag
    os.environ['TESTING'] = 'true'
    
    # Create all tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Mock the scraper factory to return our mock scraper
    def mock_get_scraper(*args, **kwargs):
        return MockScraper()
    
    with patch.object(ScraperFactory, 'get_scraper', mock_get_scraper):
        yield
        
    # Clean up
    Base.metadata.drop_all(bind=engine)
    os.environ.pop('TESTING', None)

def test_get_supported_stores(setup_database):
    with TestClient(app) as client:
        response = client.get("/supported-stores")
        assert response.status_code == 200
        stores = response.json()
        assert "albertsons" in stores
        assert "chefstore" in stores

def test_get_prices_invalid_store(setup_database):
    with TestClient(app) as client:
        response = client.post(
            "/prices",
            json={"store_name": "invalid_store", "urls": ALBERTSONS_URLS}
        )
        assert response.status_code == 400
        data = response.json()
        assert "Invalid store" in str(data["detail"])

@pytest.mark.asyncio
async def test_get_prices_with_cache(setup_database):
    with TestClient(app) as client:
        # First request to populate cache
        response = client.post(
            "/prices",
            json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check initial response structure
        assert "request_status" in data
        assert data["request_status"]["status"] in ["pending", "running"]
        
        # Wait for background task to complete
        for _ in range(20):  # Maximum retries
            await asyncio.sleep(0.2)  # Wait between retries
            response = client.post(
                "/prices",
                json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
            )
            data = response.json()
            if data["request_status"]["status"] == "completed":
                break
        
        assert data["request_status"]["status"] == "completed"
        assert data["result"]["name"] == "Test Product"
        assert data["result"]["price"] == 9.99

@pytest.mark.asyncio
async def test_concurrent_requests(setup_database):
    with TestClient(app) as client:
        # Make multiple concurrent requests
        response1 = client.post(
            "/prices",
            json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
        )
        response2 = client.post(
            "/prices",
            json={"store_name": "chefstore", "urls": CHEFSTORE_URLS}
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Wait for both requests to complete
        for _ in range(20):  # Maximum retries
            await asyncio.sleep(0.2)  # Wait between retries
            
            response1 = client.post(
                "/prices",
                json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
            )
            response2 = client.post(
                "/prices",
                json={"store_name": "chefstore", "urls": CHEFSTORE_URLS}
            )
            
            data1 = response1.json()
            data2 = response2.json()
            
            if (data1["request_status"]["status"] == "completed" and 
                data2["request_status"]["status"] == "completed"):
                break
        
        assert data1["request_status"]["status"] == "completed"
        assert data2["request_status"]["status"] == "completed"
        assert data1["result"]["name"] == "Test Product"
        assert data2["result"]["name"] == "Test Product"

@pytest.mark.asyncio
async def test_error_handling(setup_database):
    # Mock scraper that raises an error
    class ErrorScraper:
        async def get_prices(self, urls):
            raise Exception("Test error")
            
    with patch.object(ScraperFactory, 'get_scraper', return_value=ErrorScraper()):
        with TestClient(app) as client:
            response = client.post(
                "/prices",
                json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
            )
            assert response.status_code == 200
            data = response.json()
            
            # Wait for error status
            for _ in range(20):  # Increased retries
                response = client.post(
                    "/prices",
                    json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
                )
                data = response.json()
                if data["request_status"]["status"] == "failed":
                    break
                await asyncio.sleep(0.2)  # Increased delay
                
            assert data["request_status"]["status"] == "failed"
            assert "Test error" in data["request_status"]["error_message"]

def test_raw_scrape(setup_database):
    with TestClient(app) as client:
        response = client.post(
            "/raw-content",
            json={"store_name": "chefstore", "urls": CHEFSTORE_URLS}
        )
        assert response.status_code == 200
        data = response.json()
        assert "html" in data 