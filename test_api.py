import requests
import json

BASE_URL = "http://localhost:8000"

def test_health():
    response = requests.get(f"{BASE_URL}/health")
    print("\nHealth Check:")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

def test_supported_stores():
    response = requests.get(f"{BASE_URL}/supported-stores")
    print("\nSupported Stores:")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

def test_get_prices():
    data = {
        "store_name": "costco",
        "urls": [
            "https://sameday.costco.com/store/costco/products/16916808-coleman-natural-foods-organic-fresh-boneless-skinless-breast-per-lb-lb"
        ]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.post(f"{BASE_URL}/get-prices", json=data, headers=headers)
    print("\nGet Prices:")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

if __name__ == "__main__":
    print("Testing API endpoints...")
    #test_health()
    #test_supported_stores()
    test_get_prices() 