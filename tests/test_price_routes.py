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

# Constants for retry configuration
MAX_RETRIES = 60  # 5 minutes with 5-second intervals
RETRY_INTERVAL = 5  # seconds

class MockScraper:
    async def get_prices(self, urls):
        await asyncio.sleep(2)  # Simulate longer network delay
        results = {}
        for url in urls:
            results[str(url)] = {
                "store": "mock_store",
                "url": str(url),
                "name": "Test Product",
                "price": 9.99,
                "price_string": "$9.99",
                "store_id": "MOCK001",
                "store_address": "123 Mock St",
                "store_zip": "12345",
                "brand": "Mock Brand",
                "sku": "MOCK123",
                "category": "Mock Category",
                "timestamp": datetime.now(timezone.utc)
            }
        return results

    async def get_raw_content(self, urls):
        await asyncio.sleep(2)  # Simulate longer network delay
        results = {}
        for url in urls:
            results[str(url)] = {
                "content": "<html><body><h1>Test Product</h1><div class='price'>$9.99</div></body></html>",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        return results

    async def extract_product_info(self, html, url):
        # Mock the extraction process
        return {
            "store": "mock_store",
            "url": str(url),
            "name": "Test Product",
            "price": 9.99,
            "price_string": "$9.99",
            "store_id": "MOCK001",
            "store_address": "123 Mock St",
            "store_zip": "12345",
            "brand": "Mock Brand",
            "sku": "MOCK123",
            "category": "Mock Category",
            "timestamp": datetime.now(timezone.utc)
        }

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

async def wait_for_completion(client, store_name, urls, expected_status="completed"):
    """Helper function to wait for request completion."""
    for attempt in range(MAX_RETRIES):
        response = client.post(
            "/prices",
            json={"store_name": store_name, "urls": urls}
        )
        data = response.json()
        
        if isinstance(data, dict) and "request_status" in data:
            status = data["request_status"]["status"]
        else:
            status = list(data.values())[0]["request_status"]["status"]
            
        if status == expected_status:
            return data
            
        if status == "failed" and expected_status != "failed":
            raise AssertionError(f"Request failed: {data}")
            
        await asyncio.sleep(RETRY_INTERVAL)
        
    raise TimeoutError(f"Request did not reach {expected_status} status within {MAX_RETRIES * RETRY_INTERVAL} seconds")

@pytest.mark.asyncio
async def test_get_prices_with_cache(setup_database):
    with TestClient(app) as client:
        # First request to populate cache
        response = client.post(
            "/prices",
            json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
        )
        assert response.status_code == 200
        
        # Wait for completion
        data = await wait_for_completion(client, "albertsons", ALBERTSONS_URLS)
        
        assert data["request_status"]["status"] == "completed"
        assert data["result"]["name"] == "Test Product"
        assert data["result"]["price"] == 9.99
        
        # Second request should use cache
        response = client.post(
            "/prices",
            json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
        )
        data = response.json()
        assert data["request_status"]["status"] == "completed"
        assert data["result"]["name"] == "Test Product"

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
        data1 = await wait_for_completion(client, "albertsons", ALBERTSONS_URLS)
        data2 = await wait_for_completion(client, "chefstore", CHEFSTORE_URLS)
        
        assert data1["request_status"]["status"] == "completed"
        assert data2["request_status"]["status"] == "completed"
        assert data1["result"]["name"] == "Test Product"
        assert data2["result"]["name"] == "Test Product"

@pytest.mark.asyncio
async def test_error_handling(setup_database):
    # Mock scraper that raises an error
    class ErrorScraper:
        async def get_prices(self, urls):
            await asyncio.sleep(1)  # Simulate some processing time
            raise Exception("Test error")
            
    with patch.object(ScraperFactory, 'get_scraper', return_value=ErrorScraper()):
        with TestClient(app) as client:
            response = client.post(
                "/prices",
                json={"store_name": "albertsons", "urls": ALBERTSONS_URLS}
            )
            assert response.status_code == 200
            
            # Wait for error status
            data = await wait_for_completion(client, "albertsons", ALBERTSONS_URLS, expected_status="failed")
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