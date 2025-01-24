import requests
import json

url = 'http://localhost:8000/raw-scrape'
headers = {
    'accept': 'application/json',
    'Content-Type': 'application/json'
}
data = {
    'store_name': 'walmart',
    'urls': ['https://www.walmart.com/ip/319841736']
}

response = requests.post(url, headers=headers, json=data)
print(f"Status Code: {response.status_code}")
print("Response:")
print(json.dumps(response.json(), indent=2)) 