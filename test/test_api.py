import requests
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000/api/v1"

def print_response(name: str, response: requests.Response) -> None:
    print(f"\n{name}:")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response: {response.text}")
    else:
        print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_health() -> None:
    response = requests.get(f"{BASE_URL.split('/api/v1')[0]}/health")
    print_response("Health Check", response)
    assert response.status_code == 200

def test_supported_stores() -> None:
    response = requests.get(f"{BASE_URL}/prices/stores")
    print_response("Supported Stores", response)
    assert response.status_code == 200
    data = response.json()
    assert "supported_stores" in data
    assert isinstance(data["supported_stores"], list)
    assert len(data["supported_stores"]) > 0

def test_get_prices_success() -> None:
    data = {
        "store": "chefstore",
        "urls": [
            "https://www.chefstore.com/p/smithfield-menu-pride-boneless-ham_7285463",
            "https://www.chefstore.com/p/aqua-star-shrimp-peeled-tail-on-raw-31-40_8559455",
            "https://www.chefstore.com/p/boneless-beef-chuck-roll_2071225"
        ]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.post(f"{BASE_URL}/prices", json=data, headers=headers)
    print_response("Get Prices (Success)", response)
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert isinstance(data["results"], dict)

def test_get_prices_invalid_store() -> None:
    data = {
        "store": "invalid_store",
        "urls": ["https://example.com"]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.post(f"{BASE_URL}/prices", json=data, headers=headers)
    print_response("Get Prices (Invalid Store)", response)
    assert response.status_code == 400 or response.status_code == 422

def test_get_prices_invalid_url() -> None:
    data = {
        "store": "chefstore",
        "urls": ["not_a_valid_url"]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.post(f"{BASE_URL}/prices", json=data, headers=headers)
    print_response("Get Prices (Invalid URL)", response)
    assert response.status_code == 422

def test_get_raw_html() -> None:
    data = {
        "store": "chefstore",
        "urls": [
            "https://www.chefstore.com/p/smithfield-menu-pride-boneless-ham_7285463"
        ]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.get(f"{BASE_URL}/prices/raw", json=data, headers=headers)
    print_response("Get Raw HTML", response)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)

if __name__ == "__main__":
    print("Testing API endpoints...")
    try:
        test_health()
        test_supported_stores()
        test_get_prices_success()
        test_get_prices_invalid_store()
        test_get_prices_invalid_url()
        test_get_raw_html()
        print("\nAll tests completed successfully!")
    except AssertionError as e:
        print(f"\nTest failed: {str(e)}")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")