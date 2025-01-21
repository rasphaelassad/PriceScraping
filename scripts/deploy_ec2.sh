#!/bin/bash

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python and required tools
sudo apt-get install -y python3-pip python3-venv git nginx

# Create app directory
mkdir -p /home/ubuntu/app
cd /home/ubuntu/app

# Clone the repository (you'll need to replace with your actual repo URL)
# git clone <your-repo-url> .

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create systemd service file
sudo tee /etc/systemd/system/pricescraper.service << EOF
[Unit]
Description=Price Scraper FastAPI Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/app
Environment="PATH=/home/ubuntu/app/venv/bin"
Environment="SCRAPER_API_KEY=${SCRAPER_API_KEY}"
Environment="AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
Environment="AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
ExecStart=/home/ubuntu/app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx
sudo tee /etc/nginx/sites-available/pricescraper << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF

# Enable the Nginx site
sudo ln -s /etc/nginx/sites-available/pricescraper /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

# Start and enable services
sudo systemctl start pricescraper
sudo systemctl enable pricescraper
sudo systemctl restart nginx

# Show status
sudo systemctl status pricescraper 