import os
import sys
import pytest
import requests
import json
from typing import Dict, Any
from datetime import datetime
# Base URL for the running FastAPI server
base_url = os.getenv("TEST_BASE_URL", "http://localhost:8000")

def test_get_supported_stores():
    """Test the supported-stores endpoint."""
    response = requests.get(f"{base_url}/api/v1/supported-stores")
    
    # Assertions
    assert response.status_code == 200
    stores = response.json()
    assert isinstance(stores, list)
    assert len(stores) > 0
    # Verify some expected stores are in the list
    expected_stores = {"walmart", "costco", "albertsons", "chefstore"}
    assert any(store in expected_stores for store in stores)

def test_get_prices_valid_url():
    """Test the prices endpoint with a valid URL."""
    test_data = ["https://www.albertsons.com/shop/product-details.188020052.html"]
    
    response = requests.post(
        f"{base_url}/api/v1/prices", 
        json=test_data
    )
    
    # Print response for debugging
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")
    
    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    
    # Check the response structure for the URL
    url_data = data.get(test_data[0])
    assert url_data is not None
    

def test_get_prices_invalid_url():
    """Test the prices endpoint with an invalid URL."""
    test_data = ["https://invalid-store.com/product/123"]
    
    response = requests.post(f"{base_url}/api/v1/prices", json=test_data)
    
    # Assertions for error response
    assert response.status_code == 400
    error_data = response.json()
    assert "detail" in error_data
    assert "message" in error_data["detail"]
    assert "supported_stores" in error_data["detail"]
    assert "unsupported_urls" in error_data["detail"]

def test_get_prices_empty_urls():
    """Test the prices endpoint with empty URL list."""
    test_data = []
    
    response = requests.post(f"{base_url}/api/v1/prices", json=test_data)
    
    # Should return a validation error
    assert response.status_code == 422
    error_data = response.json()
    assert "detail" in error_data

def test_get_prices_multiple_urls():
    """Test the prices endpoint with multiple URLs."""
    test_data = [
        "https://www.albertsons.com/shop/product-details.188020052.html",
        "https://www.walmart.com/ip/Great-Value-2-Milk-1-Gallon/10450114"
    ]
    
    response = requests.post(f"{base_url}/api/v1/prices", json=test_data)
    
    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert len(data) == len(test_data)
    
    # Check each URL response
    for url in test_data:
        assert url in data
        url_data = data[url]
        assert isinstance(url_data, dict)
        expected_fields = {"request_status", "result"}
        assert all(field in url_data for field in expected_fields)

def test_get_raw_content():
    """Test getting raw content from a URL and saving it locally."""
    test_url = "https://www.albertsons.com/shop/product-details.188020052.html"
    
    response = requests.post(
        f"{base_url}/api/v1/raw-content",
        json=[test_url]
    )
    
    # Print response for debugging
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.json()}")
    
    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    
    # Check the response structure for the URL
    url_data = data.get(test_url)
    assert url_data is not None
    assert "content" in url_data
    
    # Save the raw content locally
    os.makedirs("test_output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_output/raw_content_{timestamp}.html"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(url_data["content"])
    
    print(f"Raw content saved to: {filename}")
    
    # Verify the file was created and has content
    assert os.path.exists(filename)
    assert os.path.getsize(filename) > 0

def check_server_health() -> bool:
    """Check if the FastAPI server is running."""
    try:
        response = requests.get(f"{base_url}/health")
        return response.status_code == 200
    except requests.ConnectionError:
        return False

if __name__ == "__main__":
    # Check if server is running before running tests
    if not check_server_health():
        print("ERROR: FastAPI server is not running!")
        print(f"Please start the server at {base_url} first")
        sys.exit(1)
    #check_server_health()    
    #test_get_supported_stores()
    #test_get_prices_valid_url()
    test_get_raw_content()
    #pytest.main([__file__, "-v"])
