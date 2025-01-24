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

# Save results to a file
output_filename = 'scrape_results.json'
with open(output_filename, 'w') as f:
    json.dump(response.json(), f, indent=2)
print(f"\nResults saved to {output_filename}") 