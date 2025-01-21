import requests
import json

BASE_URL = "http://44.202.87.88"

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
        "store_name": "walmart",
        "urls": [
            "https://www.walmart.com/ip/Great-Value-Whole-Vitamin-D-Milk-Gallon-128-fl-oz/10450114",
            "https://www.walmart.com/ip/Great-Value-Large-White-Eggs-12-Count/145051970"
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
    test_health()
    test_supported_stores()
    test_get_prices() 