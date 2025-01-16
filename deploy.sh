#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Install Serverless plugins
npm install --save-dev serverless-python-requirements

# Deploy to AWS
serverless deploy --verbose 

aws configure
# Enter your:
# - AWS Access Key ID
# - AWS Secret Access Key
# - Default region (e.g., us-east-1) 

export SCRAPER_API_KEY=your_actual_api_key 