import aiohttp
import asyncio
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid
from fastapi import HTTPException
from app.models.price_request import PriceRequest
from app.models.request_status import RequestStatus
from app.utils.parser import get_parser

class ScraperService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('SCRAPER_API_KEY')
        if not self.api_key:
            raise ValueError("ScraperAPI key not provided")
        self.session = aiohttp.ClientSession()
        self.base_url = "http://api.scraperapi.com"
        self.status_base_url = "https://api.scraperapi.com/status"

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def get_raw_content(self, request: PriceRequest) -> Dict[str, Any]:
        try:
            tasks = []
            for url in request.urls:
                tasks.append(self._fetch_url(url, request.store_name))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # For single URL requests, return just the HTML content
            if len(request.urls) == 1:
                result = results[0]
                if isinstance(result, Exception):
                    raise result
                return {"html": result["content"]}
            
            # For multiple URLs, return a dictionary with URL keys
            response = {}
            for url, result in zip(request.urls, results):
                if isinstance(result, Exception):
                    response[url] = {"error": str(result)}
                else:
                    response[url] = {"html": result["content"]}
            return response
        except Exception as e:
            logger.error(f"Error in get_raw_content: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    async def _fetch_url(self, url: str, store_name: str) -> Dict[str, Any]:
        params = {
            'api_key': self.api_key,
            'url': url,
            'render': 'true' if store_name in JAVASCRIPT_REQUIRED_STORES else 'false'
        }
        
        try:
            async with self.session.get(self.base_url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"ScraperAPI error: {error_text}")
                    raise HTTPException(status_code=response.status, detail=error_text)
                
                # Get the job ID and status URL from headers
                job_id = response.headers.get('X-ScraperAPI-JobId')
                status_url = f"{self.status_base_url}/{job_id}" if job_id else None
                
                content = await response.text()
                return {
                    "content": content,
                    "job_id": job_id,
                    "status_url": status_url,
                    "start_time": datetime.now(timezone.utc)
                }
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {e}")
            raise

    def _calculate_elapsed_time(self, start_time: Optional[datetime]) -> float:
        if not start_time:
            return 0.0
        now = datetime.now(timezone.utc)
        return (now - start_time).total_seconds()

    async def get_prices(self, request: PriceRequest) -> Dict[str, Any]:
        try:
            tasks = []
            for url in request.urls:
                tasks.append(self._process_url(url, request.store_name))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            response = {}
            for url, result in zip(request.urls, results):
                if isinstance(result, Exception):
                    response[url] = {
                        "request_status": RequestStatus(
                            status="failed",
                            error_message=str(result),
                            start_time=datetime.now(timezone.utc)
                        ).model_dump()
                    }
                else:
                    response[url] = result
            return response
        except Exception as e:
            logger.error(f"Error in get_prices: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    async def _process_url(self, url: str, store_name: str) -> Dict[str, Any]:
        try:
            # Fetch the raw content first
            raw_result = await self._fetch_url(url, store_name)
            start_time = raw_result["start_time"]
            
            # Create initial status
            status = RequestStatus(
                status="running",
                job_id=str(uuid.uuid4()),
                start_time=start_time,
                scraper_job_id=raw_result.get("job_id"),
                scraper_status_url=raw_result.get("status_url")
            )
            
            # Process the content
            html_content = raw_result["content"]
            parser = get_parser(store_name, url, html_content)
            if not parser:
                raise ValueError(f"No parser available for store: {store_name}")
            
            product_info = parser.extract_product_info()
            if not product_info:
                status.status = "failed"
                status.error_message = "Failed to extract product information"
                status.elapsed_time_seconds = self._calculate_elapsed_time(start_time)
                return {"request_status": status.model_dump()}
            
            # Update status for success
            status.status = "completed"
            status.price_found = True
            status.elapsed_time_seconds = self._calculate_elapsed_time(start_time)
            status.details = f"Request completed in {status.elapsed_time_seconds:.1f} seconds"
            
            return {
                "request_status": status.model_dump(),
                "result": product_info
            }
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            elapsed_time = self._calculate_elapsed_time(start_time if 'start_time' in locals() else None)
            return {
                "request_status": RequestStatus(
                    status="failed",
                    error_message=str(e),
                    start_time=start_time if 'start_time' in locals() else datetime.now(timezone.utc),
                    elapsed_time_seconds=elapsed_time,
                    details=f"Request failed after {elapsed_time:.1f} seconds"
                ).model_dump()
            } 