import requests
import json
import logging
import sys
import time
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from app.main import app

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api/v1"

def test_health():
    try:
        response = requests.get(f"{BASE_URL}/health")
        print("\nHealth Check:")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        assert response.status_code == 200, "Health check failed"
        return True
    except Exception as e:
        print(f"Health check error: {e}")
        return False

def test_supported_stores():
    try:
        response = requests.get(f"{BASE_URL}/supported-stores")
        print("\nSupported Stores:")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        assert response.status_code == 200, "Supported stores check failed"
        stores = response.json()
        assert isinstance(stores, list), "Supported stores should be a list"
        assert len(stores) > 0, "No supported stores found"
        return True
    except Exception as e:
        print(f"Supported stores error: {e}")
        return False

def test_get_prices():
    try:
        data = {
            "store_name": "albertsons",
            "urls": [
                "https://www.albertsons.com/shop/product-details.960444189.html",
                "https://www.albertsons.com/shop/product-details.960109087.html"
            ]
        }
        
        # Initial request
        response = requests.post(f"{BASE_URL}/prices", json=data)
        print("\nGet Prices (Initial Request):")
        print(f"Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            print(f"Error Response: {response.text}")
            return False
            
        try:
            json_response = response.json()
            print(f"Initial Response: {json.dumps(json_response, indent=2)}")
            
            # Validate response structure
            assert isinstance(json_response, dict), "Response should be a dictionary"
            
            for url, result in json_response.items():
                assert isinstance(result, dict), f"Result for {url} should be a dictionary"
                assert "request_status" in result, f"Result for {url} missing 'request_status'"
                
                status = result["request_status"]
                assert "status" in status, "request_status missing 'status' field"
                assert "job_id" in status, "request_status missing 'job_id' field"
                assert "start_time" in status, "request_status missing 'start_time' field"
                assert "elapsed_time_seconds" in status, "request_status missing 'elapsed_time_seconds' field"
                
                # Verify elapsed time is reasonable
                assert 0 <= status["elapsed_time_seconds"] <= 300, "Elapsed time should be between 0 and 300 seconds"
                
                # Verify scraper job fields if present
                if status.get("scraper_job_id"):
                    assert status.get("scraper_status_url"), "Missing scraper_status_url when scraper_job_id is present"
                    assert status["scraper_status_url"].startswith("https://api.scraperapi.com/status/"), "Invalid scraper status URL format"
                
                # If initial response has the result, validate it
                if result.get("result"):
                    product = result["result"]
                    assert "store" in product, "Product missing 'store' field"
                    assert "url" in product, "Product missing 'url' field"
                    assert "name" in product, "Product missing 'name' field"
                # If no result yet, wait and try again
                else:
                    print("\nWaiting for background processing...")
                    max_retries = 12  # 1 minute total (5 seconds * 12)
                    initial_elapsed_time = status["elapsed_time_seconds"]
                    
                    for i in range(max_retries):
                        time.sleep(5)  # Wait 5 seconds between retries
                        response = requests.post(f"{BASE_URL}/prices", json=data)
                        if response.status_code == 200:
                            retry_response = response.json()
                            print(f"Retry {i+1} Response: {json.dumps(retry_response, indent=2)}")
                            
                            # Check if we have results
                            retry_result = retry_response[url]
                            retry_status = retry_result["request_status"]
                            
                            # Verify elapsed time is increasing reasonably
                            assert retry_status["elapsed_time_seconds"] >= initial_elapsed_time, "Elapsed time should not decrease"
                            assert retry_status["elapsed_time_seconds"] <= initial_elapsed_time + 300, "Elapsed time increase too large"
                            
                            if retry_result.get("result"):
                                product = retry_result["result"]
                                assert "store" in product, "Product missing 'store' field"
                                assert "url" in product, "Product missing 'url' field"
                                assert "name" in product, "Product missing 'name' field"
                                break
                            elif retry_status["status"] in ["failed", "timeout"]:
                                print(f"Request failed: {retry_status}")
                                break
                        else:
                            print(f"Retry {i+1} failed with status {response.status_code}")
            
            return True
            
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON response: {e}")
            print(f"Raw response text: {response.text}")
            return False
            
    except Exception as e:
        print(f"Get prices error: {e}")
        return False

def test_raw_content():
    try:
        data = {
            "store_name": "albertsons",
            "urls": ["https://www.albertsons.com/shop/product-details.960444189.html"]
        }
        
        response = requests.post(f"{BASE_URL}/raw-content", json=data)
        print("\nRaw Content Request:")
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error Response: {response.text}")
            return False
            
        json_response = response.json()
        print(f"Response: {json.dumps(json_response, indent=2)}")
        
        # For single URL, verify we get HTML content
        assert "html" in json_response, "Response missing HTML content"
        assert isinstance(json_response["html"], str), "HTML content should be a string"
        
        return True
        
    except Exception as e:
        print(f"Raw content error: {e}")
        return False

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

if __name__ == "__main__":
    print("Testing API endpoints...")
    success = True
    
    
    if not test_get_prices():
        print("Get prices check failed")
        success = False
    
    if not success:
        print("\nSome tests failed!")
        sys.exit(1)
    else:
        print("\nAll tests passed!")

