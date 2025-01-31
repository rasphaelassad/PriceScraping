from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal, Any
import logging
import httpx
import time
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone
from urllib.parse import urlparse
from app.core.config import get_settings
from app.schemas.request_schemas import ensure_utc_datetime, ProductInfo
from app.core.cache_manager import CacheManager
from app.models.database import get_db
from fastapi import HTTPException
import aiohttp
import uuid

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Base class for all store-specific scrapers."""

    INITIAL_WAIT = 60  # Initial wait time of 1 minute
    TIMEOUT_MINUTES = 15  # Maximum timeout of 15 minutes
    MAX_ACTIVE_JOBS = 1000  # Maximum number of active jobs to prevent memory leaks
    
    def __init__(self, mode: Literal["batch", "async"] = "batch"):
        """
        Initialize the scraper.
        
        Args:
            mode: Either "batch" for batch processing or "async" for individual concurrent requests
        """
        self.settings = get_settings()
        self.api_key = self.settings.scraper_api_key
        self.mode = mode
        self.base_url = "https://async.scraperapi.com/jobs"
        self.batch_url = "https://async.scraperapi.com/batchjobs"
        self.store_name = None
        self._active_jobs = {}  # Store active jobs by URL
        self._job_cleanup_time = time.time()  # Track last cleanup time
        logger.info(f"Initialized {self.__class__.__name__} in {mode} mode")

    def _validate_url(self, url: str) -> bool:
        """Validate URL format and domain"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def _cleanup_old_jobs(self) -> None:
        """Clean up old jobs to prevent memory leaks"""
        current_time = time.time()
        # Only clean up every 5 minutes
        if current_time - self._job_cleanup_time < 300:
            return
            
        self._job_cleanup_time = current_time
        expired_urls = []
        
        for url, job_info in self._active_jobs.items():
            if current_time - job_info['start_time'] > self.TIMEOUT_MINUTES * 60:
                expired_urls.append(url)
                
        for url in expired_urls:
            self._active_jobs.pop(url, None)
            logger.info(f"Cleaned up expired job for URL: {url}")

    async def get_raw_content(self, urls: List[str]) -> Dict[str, Dict]:
        """Get raw HTML/JSON content for URLs without processing"""
        # Validate URLs and convert to strings
        validated_urls = []
        invalid_urls = {}
        
        for url in urls:
            url_str = str(url)
            if self._validate_url(url_str):
                validated_urls.append(url_str)
            else:
                invalid_urls[url_str] = {
                    "error": "Invalid URL format",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
        
        # Clean up old jobs before processing new ones
        self._cleanup_old_jobs()
        
        # Check if we have too many active jobs
        if len(self._active_jobs) >= self.MAX_ACTIVE_JOBS:
            error_msg = "Too many active jobs, try again later"
            return {url: {
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat()
            } for url in validated_urls} | invalid_urls
        
        results = {}
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                if self.mode == "batch":
                    results = await self._get_raw_batch(validated_urls, client)
                else:
                    tasks = [self._get_raw_single(url, client) for url in validated_urls]
                    task_results = await asyncio.gather(*tasks)
                    results = dict(zip(validated_urls, task_results))
            except Exception as e:
                logger.error(f"Error in get_raw_content: {str(e)}")
                results = {url: {
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                } for url in validated_urls}
                
        # Combine results with invalid URLs
        return results | invalid_urls

    @abstractmethod
    def get_scraper_config(self) -> Dict:
        """
        Return scraper configuration for the specific store.
        Must be implemented by child classes.
        
        Returns:
            Dict: Configuration parameters for the scraper
        """
        pass

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Dict:
        """
        Extract all product information from HTML content.
        Must be implemented by child classes.
        
        Args:
            html (str): Raw HTML content
            url (str): Product URL
            
        Returns:
            Dict: Extracted product information
        """
        pass

    async def _get_raw_single(self, url: str, client: httpx.AsyncClient) -> Dict:
        """Get raw content for a single URL"""
        try:
            # Check if we already have an active job for this URL
            if url in self._active_jobs:
                job_info = self._active_jobs[url]
                status_url = job_info['status_url']
                job_id = job_info['job_id']
                start_time = job_info['start_time']
                logger.info(f"Found existing job {job_id} for URL {url}")
            else:
                # Create new job only if we don't have one
                config = self.get_scraper_config()
                payload = {
                    "url": url,
                    "apiKey": self.api_key,
                    **config
                }
                
                logger.info(f"Creating new job for URL: {url}")
                
                response = await client.post(self.base_url, json=payload)
                if response.status_code != 200:
                    error_msg = f"API request failed with status {response.status_code}"
                    logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                job_data = response.json()
                job_id = job_data.get('id')
                status_url = job_data.get('statusUrl')

                if not job_id:
                    error_msg = "No job ID received"
                    logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                
                # Store the new job info
                start_time = time.time()
                self._active_jobs[url] = {
                    'job_id': job_id,
                    'status_url': status_url,
                    'start_time': start_time
                }

            # Poll for job status
            elapsed_time = time.time() - start_time
            initial_timeout = False
            
            # Check if we've exceeded the maximum timeout
            if elapsed_time / 60 >= self.TIMEOUT_MINUTES:
                error_msg = f"Job {job_id} timed out after {self.TIMEOUT_MINUTES} minutes"
                logger.error(error_msg)
                # Clean up the stored job
                self._active_jobs.pop(url, None)
                return {
                    "error": error_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Check if we should return early for initial timeout
            if elapsed_time >= self.INITIAL_WAIT and not initial_timeout:
                initial_timeout = True
                logger.info(f"Initial wait time exceeded for job {job_id}, returning no price info")
                return {
                    "status": "pending",
                    "job_id": job_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "Job still running, check back later"
                }

            status_response = await client.get(status_url)
            if status_response.status_code != 200:
                if initial_timeout:
                    return {
                        "status": "pending",
                        "job_id": job_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": "Job still running, check back later"
                    }
                error_msg = f"Status check failed with status {status_response.status_code}"
                logger.error(error_msg)
                # Clean up the stored job
                self._active_jobs.pop(url, None)
                return {
                    "error": error_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            try:
                status_data = status_response.json()
            except Exception as e:
                if initial_timeout:
                    return {
                        "status": "pending",
                        "job_id": job_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": "Job still running, check back later"
                    }
                error_msg = f"Failed to parse status response: {str(e)}"
                logger.error(error_msg)
                # Clean up the stored job
                self._active_jobs.pop(url, None)
                return {
                    "error": error_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            status = status_data.get('status')
            logger.debug(f"Job {job_id} status: {status}")

            if status == 'failed':
                error_msg = f"Job {job_id} failed: {status_data.get('error', 'Unknown error')}"
                logger.error(error_msg)
                # Clean up the stored job
                self._active_jobs.pop(url, None)
                return {
                    "error": error_msg,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            elif status == 'finished':
                response_data = status_data.get('response', {})
                html = response_data.get('body')
                if html:
                    logger.info(f"Job {job_id} completed successfully")
                    # Clean up the stored job on success
                    self._active_jobs.pop(url, None)
                    return {
                        "content": html,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "start_time": datetime.now(timezone.utc)
                    }
                else:
                    error_msg = f"No content in response for job {job_id}"
                    logger.error(error_msg)
                    # Clean up the stored job
                    self._active_jobs.pop(url, None)
                    return {
                        "error": error_msg,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

            # Job is still running
            return {
                "status": "pending",
                "job_id": job_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": "Job still running, check back later"
            }

        except Exception as e:
            error_msg = f"Unexpected error in _get_raw_single: {str(e)}"
            logger.error(error_msg)
            # Clean up the stored job
            self._active_jobs.pop(url, None)
            return {
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def _get_raw_batch(self, urls: List[str], client: httpx.AsyncClient) -> Dict[str, Dict]:
        """Get raw content for multiple URLs using batch processing"""
        try:
            payload = {
                "urls": urls,
                "apiKey": self.api_key,
                "apiParams": self.get_scraper_config()
            }

            response = await client.post(self.batch_url, json=payload)
            if response.status_code != 200:
                return {url: {
                    "error": f"Batch API request failed with status {response.status_code}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                } for url in urls}

            jobs = response.json()
            job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}
            results = {}
            start_time = time.time()

            while any(status['status'] == 'running' for status in job_statuses.values()):
                if (time.time() - start_time) / 60 >= self.TIMEOUT_MINUTES:
                    for job_info in job_statuses.values():
                        if job_info['status'] == 'running':
                            results[job_info['url']] = {
                                "error": "Job timed out",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                    break

                for job_id, job_info in job_statuses.items():
                    if job_info['status'] == 'running':
                        status_response = await client.get(job_info['statusUrl'])
                        status_data = status_response.json()
                        current_status = status_data.get('status')
                        
                        if current_status == 'failed':
                            job_info['status'] = 'failed'
                            results[job_info['url']] = {
                                "error": "Job failed",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        elif current_status == 'finished':
                            job_info['status'] = 'finished'
                            html = status_data.get('response', {}).get('body')
                            if html:
                                results[job_info['url']] = {
                                    "content": html,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }
                            else:
                                results[job_info['url']] = {
                                    "error": "No HTML content in response",
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }

                await asyncio.sleep(5)

            # Fill in any missing results
            for url in urls:
                if url not in results:
                    results[url] = {
                        "error": "Job processing failed",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

            return results

        except Exception as e:
            return {url: {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            } for url in urls}

    async def get_price(self, url: str) -> Dict[str, Any]:
        """Get price for a single URL."""
        try:
            # First check product cache
            with get_db() as db:
                cache_manager = CacheManager(db)
                cached_product = await cache_manager.get_cached_product(url, self.store_name)
                
                if cached_product:
                    logger.info(f"Found cached product for {url}")
                    return {
                        "product_info": cached_product,
                        "request_status": {
                            "status": "success",
                            "start_time": datetime.now(timezone.utc),
                            "elapsed_time_seconds": 0.0,
                            "job_id": str(uuid.uuid4()),
                            "cached": True
                        }
                    }

                # Check for existing job
                existing_request = cache_manager._get_latest_request(url, self.store_name, db)
                if existing_request and existing_request.status in ['pending', 'running']:
                    logger.info(f"Found existing job for {url}")
                    # Check job status
                    async with httpx.AsyncClient(verify=False) as client:
                        status_response = await client.get(existing_request.status_url)
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            if status_data.get('status') == 'finished':
                                # Job completed, process the result
                                html = status_data.get('response', {}).get('body')
                                if html:
                                    product_info = await self.extract_product_info(html, url)
                                    if product_info:
                                        standardized_info = self.standardize_output(product_info)
                                        if standardized_info:
                                            # Cache the result
                                            product_info_obj = ProductInfo(**standardized_info)
                                            cache_manager.cache_product(product_info_obj)
                                            cache_manager.update_request_status(url, self.store_name, 'completed')
                                            return {
                                                "product_info": standardized_info,
                                                "request_status": {
                                                    "status": "success",
                                                    "start_time": existing_request.start_time,
                                                    "elapsed_time_seconds": (datetime.now(timezone.utc) - existing_request.start_time).total_seconds(),
                                                    "job_id": existing_request.job_id,
                                                    "cached": False
                                                }
                                            }
                            elif status_data.get('status') == 'failed':
                                # Job failed, clean up and create new job
                                cache_manager.update_request_status(url, self.store_name, 'failed', status_data.get('error'))
                            else:
                                # Job still running
                                return {
                                    "request_status": {
                                        "status": "pending",
                                        "start_time": existing_request.start_time,
                                        "elapsed_time_seconds": (datetime.now(timezone.utc) - existing_request.start_time).total_seconds(),
                                        "job_id": existing_request.job_id,
                                        "message": "Job still running"
                                    }
                                }

                # No cached product and no running job, create new job
                api_url = self.transform_url(url)  # This will be different for Albertsons
                config = self.get_scraper_config()
                
                # Create new job
                async with httpx.AsyncClient(verify=False) as client:
                    payload = {
                        "url": api_url,
                        "apiKey": self.api_key,
                        **config
                    }
                    
                    logger.info(f"Creating new job for URL: {url}")
                    response = await client.post(self.base_url, json=payload)
                    
                    if response.status_code != 200:
                        error_msg = f"API request failed with status {response.status_code}"
                        logger.error(error_msg)
                        raise ValueError(error_msg)

                    job_data = response.json()
                    job_id = job_data.get('id')
                    status_url = job_data.get('statusUrl')

                    if not job_id:
                        error_msg = "No job ID received"
                        logger.error(error_msg)
                        raise ValueError(error_msg)

                    # Create pending request in cache
                    request_status = cache_manager.create_pending_request(url, self.store_name)
                    cache_manager.update_request_status(url, self.store_name, 'running')

                    return {
                        "request_status": {
                            "status": "pending",
                            "start_time": datetime.now(timezone.utc),
                            "elapsed_time_seconds": 0.0,
                            "job_id": job_id,
                            "message": "Job created and running"
                        }
                    }
            
        except Exception as e:
            error_msg = f"Error getting price for {url}: {str(e)}"
            logger.error(error_msg)
            return {
                "request_status": {
                    "status": "failed",
                    "error_message": str(e),
                    "start_time": datetime.now(timezone.utc),
                    "elapsed_time_seconds": 0.0,
                    "job_id": str(uuid.uuid4())
                }
            }

    def transform_url(self, url: str) -> str:
        """Transform product detail URL to API URL. Override in subclass."""
        return url

    def standardize_output(self, product_info: Dict) -> Optional[Dict]:
        """
        Standardize the output format across all scrapers
        
        Args:
            product_info (Dict): Raw product information
            
        Returns:
            Optional[Dict]: Standardized product info or None if invalid
        """
        if not product_info:
            return None
        
        try:
            standardized = {
                "store": str(product_info.get("store", "")),
                "url": str(product_info.get("url", "")),
                "name": str(product_info.get("name", "")),
                "price": float(product_info["price"]) if product_info.get("price") not in [None, "", "None"] else None,
                "price_string": str(product_info.get("price_string", "")) or None,
                "price_per_unit": float(product_info.get("price_per_unit")) if product_info.get("price_per_unit") not in [None, "", "None"] else None,
                "price_per_unit_string": str(product_info.get("price_per_unit_string", "")) or None,
                "store_id": str(product_info.get("store_id", "")) or None,
                "store_address": str(product_info.get("store_address", "")) or None,
                "store_zip": str(product_info.get("store_zip", "")) or None,
                "brand": str(product_info.get("brand", "")) or None,
                "sku": str(product_info.get("sku", "")) or None,
                "category": str(product_info.get("category", "")) or None
            }
            return standardized
        except Exception as e:
            logger.error(f"Error standardizing output: {str(e)}")
            return None