import requests
import json
import logging
import sys
import time
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"

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
        data = response.json()
        assert "supported_stores" in data, "Missing supported_stores in response"
        assert isinstance(data["supported_stores"], list), "supported_stores should be a list"
        return True
    except Exception as e:
        print(f"Supported stores error: {e}")
        return False

def test_get_prices():
    try:
        now = datetime.now(timezone.utc)
        data = {
            "store_name": "chefstore",
            "urls": [
                "https://www.chefstore.com/p/smithfield-menu-pride-boneless-ham_7285463"
            ],
            "start_time": now.isoformat()
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Initial request
        response = requests.post(f"{BASE_URL}/get-prices", json=data, headers=headers)
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
            assert "results" in json_response, "Response missing 'results' field"
            
            results = json_response["results"]
            for url, result in results.items():
                assert isinstance(result, dict), f"Result for {url} should be a dictionary"
                assert "request_status" in result, f"Result for {url} missing 'request_status'"
                
                status = result["request_status"]
                assert "status" in status, "request_status missing 'status' field"
                assert "job_id" in status, "request_status missing 'job_id' field"
                
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
                    for i in range(max_retries):
                        time.sleep(5)  # Wait 5 seconds between retries
                        # Use the same start_time for retries
                        response = requests.post(f"{BASE_URL}/get-prices", json=data, headers=headers)
                        if response.status_code == 200:
                            retry_response = response.json()
                            print(f"Retry {i+1} Response: {json.dumps(retry_response, indent=2)}")
                            
                            # Check if we have results
                            retry_result = retry_response["results"][url]
                            if retry_result.get("result"):
                                product = retry_result["result"]
                                assert "store" in product, "Product missing 'store' field"
                                assert "url" in product, "Product missing 'url' field"
                                assert "name" in product, "Product missing 'name' field"
                                break
                            elif retry_result["request_status"]["status"] in ["failed", "timeout"]:
                                print(f"Request failed: {retry_result['request_status']}")
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