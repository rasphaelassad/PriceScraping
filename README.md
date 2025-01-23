# Store Price API

A FastAPI-based application that scrapes product prices from different online stores using ScraperAPI. Supports multiple stores with store-specific configurations and parsing logic.

## Features

- Batch scraping of multiple URLs
- Async processing using ScraperAPI's batch endpoint
- Store-specific configurations and parsing
- Comprehensive product information including prices, metadata, and details
- AWS Lambda deployment ready
- 24-hour caching system to reduce API calls and improve response times
- Standardized output format across all stores

## Project Structure 

```
app/
├── __init__.py
├── main.py                 # FastAPI application
├── models/
│   └── database.py        # SQLAlchemy models for caching
├── schemas/
│   └── request_schemas.py # Pydantic models for API
└── scrapers/
    ├── __init__.py
    ├── base_scraper.py    # Base scraper with common functionality
    ├── walmart_scraper.py
    ├── costco_scraper.py
    ├── albertsons_scraper.py
    └── chefstore_scraper.py
```

## Standardized Output Format

All scrapers return product information in a standardized format:

```json
{
    "store": "store_name",
    "url": "product_url",
    "name": "product_name",
    "price": 0.00,
    "price_string": "$0.00",
    "price_per_unit": 0.00,
    "price_per_unit_string": "$0.00/lb",
    "store_id": "store_identifier",
    "store_address": "store_location",
    "store_zip": "store_zipcode",
    "brand": "product_brand",
    "sku": "product_sku",
    "category": "product_category"
}
```

## Caching System

The application includes a SQLite-based caching system that:
- Stores product information for 24 hours
- Reduces API calls to external services
- Improves response times for frequently requested products
- Automatically updates cached data when it expires

## Setup and Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Set up environment variables:
```bash
SCRAPER_API_KEY=your_api_key_here
```
4. Run the application:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

- `GET /`: Welcome message
- `GET /health`: Health check endpoint
- `GET /supported-stores`: List of supported stores
- `POST /get-prices`: Get prices for products
  - Request body:
    ```json
    {
        "store_name": "store_name",
        "urls": ["product_url1", "product_url2"]
    }
    ```

## Cache Management

The cache automatically:
- Expires entries after 24 hours
- Updates when new data is fetched
- Maintains data consistency across requests
