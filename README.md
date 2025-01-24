# Store Price API

A FastAPI-based application that scrapes product prices from various online grocery stores and retailers. The system provides a unified API interface for retrieving product information and prices across different stores while implementing efficient caching and standardized output formats.

## Features

- Multi-store support (Walmart, Albertsons, ChefStore, and more)
- Efficient price scraping with store-specific implementations
- SQLite-based caching system for improved performance
- Standardized JSON output format across all stores
- Comprehensive error handling and logging
- Automated test suite for scrapers and API endpoints
- Configurable scraping parameters per store

## Project Structure 

```
app/
├── __init__.py
├── main.py                # FastAPI application entry point
├── models/
│   └── database.py       # SQLite database models
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py   # Abstract base scraper class
│   ├── albertsons_scraper.py
│   ├── chefstore_scraper.py
│   └── walmart_scraper.py
└── schemas/              # API request/response schemas

test/
├── test_api.py          # API endpoint tests
├── test_raw_scrape.py   # Scraper implementation tests
└── scrape_results.json  # Test results cache

data/                    # Database and persistent storage
└── scraper.db          # SQLite database file
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

## Setup and Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd PriceScraping
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\activate   # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
# Create a .env file with the following:
SCRAPER_API_KEY=your_api_key_here
DATABASE_URL=sqlite:///data/scraper.db
```

5. Run the application:
```bash
python run.py
# or
uvicorn app.main:app --reload
```

## API Endpoints

### Base Endpoints
- `GET /`: Welcome message and API status
- `GET /health`: Health check endpoint
- `GET /supported-stores`: List of supported stores and their configurations

### Price Scraping
- `POST /get-prices`: Retrieve prices for products
  - Request body:
    ```json
    {
        "store_name": "store_name",
        "urls": ["product_url1", "product_url2"]
    }
    ```
  - Response: JSON array of standardized product information

## Testing

Run the test suite:
```bash
pytest
```

The test suite includes:
- API endpoint tests
- Individual scraper tests
- Database model tests
- Integration tests

## Cache Management

The SQLite-based caching system:
- Stores successful scrape results for 24 hours
- Automatically invalidates old entries
- Reduces API calls and improves response times
- Handles concurrent requests efficiently

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
