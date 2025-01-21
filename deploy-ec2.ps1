# AWS Configuration
$region = "us-east-1"
$instanceType = "t2.micro"
$amiId = "ami-0c7217cdde317cfec"  # Amazon Linux 2023 AMI
$keyPairName = "store-price-api-key"
$securityGroupName = "store-price-api-sg"
$instanceName = "store-price-api"

# Check AWS CLI installation and credentials
Write-Host "Checking AWS CLI configuration..."
try {
    aws sts get-caller-identity | Out-Null
} catch {
    Write-Error "AWS CLI is not configured. Please run 'aws configure' first."
    exit 1
}

# Delete existing key pair if it exists
Write-Host "Setting up key pair..."
aws ec2 delete-key-pair --key-name $keyPairName --region $region 2>$null

# Create new key pair
Write-Host "Creating new key pair..."
aws ec2 create-key-pair --key-name $keyPairName --query 'KeyMaterial' --output text --region $region > "${keyPairName}.pem"
if ($LASTEXITCODE -eq 0) {
    Write-Host "Created new key pair"
    # Secure the key file
    icacls "${keyPairName}.pem" /inheritance:r
    icacls "${keyPairName}.pem" /grant:r "$($env:USERNAME):(R)"
} else {
    Write-Error "Failed to create key pair"
    exit 1
}

# Delete existing security group if it exists
Write-Host "Setting up security group..."
$existingGroupId = (aws ec2 describe-security-groups --group-names $securityGroupName --query 'SecurityGroups[0].GroupId' --output text --region $region 2>$null)
if ($existingGroupId -and $existingGroupId -ne "None") {
    Write-Host "Deleting existing security group..."
    aws ec2 delete-security-group --group-id $existingGroupId --region $region
}

# Create new security group
Write-Host "Creating new security group..."
$securityGroupId = (aws ec2 create-security-group --group-name $securityGroupName --description "Security group for store-price-api" --region $region --query 'GroupId' --output text)

if ($securityGroupId) {
    Write-Host "Created security group: $securityGroupId"
    
    # Add inbound rules
    aws ec2 authorize-security-group-ingress --group-id $securityGroupId --protocol tcp --port 22 --cidr 0.0.0.0/0 --region $region
    aws ec2 authorize-security-group-ingress --group-id $securityGroupId --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $region
    aws ec2 authorize-security-group-ingress --group-id $securityGroupId --protocol tcp --port 8000 --cidr 0.0.0.0/0 --region $region
    Write-Host "Added inbound rules to security group"
} else {
    Write-Error "Failed to create security group"
    exit 1
}

# Create user data script
$userData = @"
#!/bin/bash
# Update system
dnf update -y

# Install Docker
dnf install -y docker
systemctl start docker
systemctl enable docker

# Create application directory
mkdir -p /home/ec2-user/store-price-api
cd /home/ec2-user/store-price-api

# Create necessary files
cat > requirements.txt << 'EOL'
fastapi==0.109.0
mangum==0.17.0
uvicorn==0.27.0
httpx==0.26.0
aws-lambda-powertools==2.31.0
parsel==1.8.1
python-dotenv==1.0.1
EOL

cat > Dockerfile << 'EOL'
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y gcc python3-dev libxml2-dev libxslt-dev libffi-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy environment variables
COPY .env .

# Copy application code
COPY app ./app
COPY run.py .

# Expose port
EXPOSE 8000

# Run the FastAPI application
CMD ["python", "run.py"]
EOL

# Create environment file
echo "SCRAPER_API_KEY=fd20f9e6bd970af34cc011eed44a2f0d" > .env

# Create app directory and files
mkdir -p app/scrapers

cat > run.py << 'EOL'
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
EOL

cat > app/main.py << 'EOL'
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Optional
from app.scrapers.walmart_scraper import WalmartScraper

app = FastAPI()
walmart_scraper = WalmartScraper()

class PriceRequest(BaseModel):
    store_name: str
    urls: List[HttpUrl]

class PriceResponse(BaseModel):
    results: Dict
    error: Optional[str] = None

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/supported-stores")
def get_supported_stores():
    return {"supported_stores": ["walmart", "albertsons"]}

@app.post("/get-prices")
async def get_prices(request: PriceRequest):
    if request.store_name.lower() != "walmart":
        raise HTTPException(status_code=400, detail="Unsupported store")
    
    try:
        results = await walmart_scraper.get_prices(request.urls)
        return PriceResponse(results=results)
    except Exception as e:
        return PriceResponse(results={}, error=str(e))
EOL

cat > app/scrapers/base_scraper.py << 'EOL'
from abc import ABC, abstractmethod
from typing import Dict, List
import logging
import httpx
import time
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    API_KEY = os.environ["SCRAPER_API_KEY"]

    def __init__(self):
        self.scraper_config = self.get_scraper_config()

    @abstractmethod
    def get_scraper_config(self) -> Dict:
        """Return scraper configuration for the specific store"""
        pass

    @abstractmethod
    async def extract_product_info(self, html: str, url: str) -> Dict:
        """Extract all product information from HTML content"""
        pass

    async def get_prices(self, urls: List[str]) -> Dict[str, Dict]:
        """Get product information for multiple URLs in a single batch request"""
        results = {}
        url_strings = [str(url) for url in urls]
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                api_url = "https://async.scraperapi.com/batchjobs"
                payload = {
                    "urls": url_strings,
                    "apiKey": self.API_KEY,
                    "apiParams": self.scraper_config
                }

                logger.info(f"Sending request to {api_url}")
                logger.info(f"Payload: {payload}")

                response = await client.post(api_url, json=payload)
                logger.info(f"Response status: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"API request failed with status {response.status_code}")
                    logger.error(f"Response body: {response.text}")
                    return {url: None for url in urls}
                
                jobs = response.json()
                job_statuses = {job['id']: {'status': 'running', 'url': job['url'], 'statusUrl': job['statusUrl']} for job in jobs}

                while any(status['status'] == 'running' for status in job_statuses.values()):
                    for job_id, job_info in job_statuses.items():
                        if job_info['status'] == 'running':
                            status_response = await client.get(job_info['statusUrl'])
                            status_data = status_response.json()
                            current_status = status_data.get('status')
                            logger.info(f"Job {job_id} for URL {job_info['url']} status: {current_status}")
                            
                            if current_status == 'failed':
                                logger.info(f"Setting job {job_id} to failed")
                                job_info['status'] = 'failed'
                                results[job_info['url']] = None
                            elif current_status == 'finished':
                                logger.info(f"Setting job {job_id} to finished")
                                job_info['status'] = 'finished'
                                html = status_data.get('response', {}).get('body')
                                if html:
                                    try:
                                        product_info = await self.extract_product_info(html, job_info['url'])
                                        results[job_info['url']] = product_info
                                    except Exception as e:
                                        logger.error(f"Error processing URL {job_info['url']}: {str(e)}")
                                        results[job_info['url']] = None
                                else:
                                    logger.error(f"No HTML content in response for job {job_id}")
                                    results[job_info['url']] = None

                    await asyncio.sleep(5)

                for url in urls:
                    if str(url) not in results:
                        results[str(url)] = None

            except Exception as e:
                logger.error(f"Error in batch processing: {str(e)}")
                results = {str(url): None for url in urls}

        logger.info(f"Final results before return: {results}")
        return results
EOL

cat > app/scrapers/walmart_scraper.py << 'EOL'
from typing import Dict
import parsel
from .base_scraper import BaseScraper, logger

class WalmartScraper(BaseScraper):
    def get_scraper_config(self) -> Dict:
        return {
            "country_code": "us",
            "premium": True,
            "render_js": True
        }

    async def extract_product_info(self, html: str, url: str) -> Dict:
        selector = parsel.Selector(text=html)
        
        # Extract product name
        name = selector.css('[itemprop="name"]::text').get()
        if not name:
            name = selector.css('h1[data-testid="product-title"]::text').get()
        
        # Extract price
        price_string = selector.css('span[itemprop="price"]::text').get()
        if not price_string:
            price_string = selector.css('[data-testid="price-per-unit"]::text').get()
        
        if not price_string:
            logger.error(f"Could not find price for URL: {url}")
            return None
        
        try:
            # Convert price string to float
            price = float(price_string.strip('¢').strip('$')) / 100 if '¢' in price_string else float(price_string.strip('$'))
            
            return {
                "store": "walmart",
                "url": url,
                "name": name.strip() if name else None,
                "price": price,
                "price_string": price_string.strip() if price_string else None
            }
        except (ValueError, AttributeError) as e:
            logger.error(f"Error processing price for URL {url}: {str(e)}")
            return None
EOL

# Set permissions
chown -R ec2-user:ec2-user /home/ec2-user/store-price-api

# Build and run Docker container
cd /home/ec2-user/store-price-api
docker build -t store-price-api .
docker run -d -p 80:8000 store-price-api
"@

# Convert user data to base64
$userDataBase64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($userData))

# Launch EC2 instance
Write-Host "Launching EC2 instance..."
try {
    $instanceId = (aws ec2 run-instances `
        --image-id $amiId `
        --instance-type $instanceType `
        --key-name $keyPairName `
        --security-group-ids $securityGroupId `
        --user-data $userDataBase64 `
        --region $region `
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$instanceName}]" `
        --query 'Instances[0].InstanceId' `
        --output text)

    if (-not $instanceId) {
        Write-Error "Failed to get instance ID"
        exit 1
    }

    Write-Host "Instance ID: $instanceId"
    Write-Host "Waiting for instance to be running..."
    aws ec2 wait instance-running --instance-ids $instanceId --region $region

    # Get instance public IP
    $publicIp = (aws ec2 describe-instances --instance-ids $instanceId --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --region $region)

    Write-Host "`nDeployment completed!"
    Write-Host "Instance ID: $instanceId"
    Write-Host "Public IP: $publicIp"
    Write-Host "Application will be available at: http://${publicIp}"
    Write-Host "To SSH into the instance: ssh -i ${keyPairName}.pem ec2-user@${publicIp}"
    Write-Host "Note: It may take a few minutes for the instance to complete initialization and start the application."
} catch {
    Write-Error "Failed to launch EC2 instance: $_"
    exit 1
}