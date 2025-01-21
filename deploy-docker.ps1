# Script to build and deploy Docker container locally
aws ecr delete-repository --repository-name store-price-api-dev --force
# Load environment variables from .env file
function Load-EnvFile {
    $envFile = ".\.env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                Write-Host "Loading env variable: $key"
                [Environment]::SetEnvironmentVariable($key, $value, "Process")
            }
        }
    }
}

# Clean up Docker system
Write-Host "Cleaning Docker system..."
docker system prune -af

# Load environment variables
Write-Host "Loading environment variables..."
Load-EnvFile

# Build Docker image
Write-Host "Building Docker image..."
docker build --platform linux/amd64 -t store-price-api:latest .

# Check if container is already running
$containerId = docker ps -q --filter "name=store-price-api"
if ($containerId) {
    Write-Host "Stopping existing container..."
    docker stop store-price-api
    docker rm store-price-api
}

# Run the container
Write-Host "Starting container..."
docker run -d `
    --name store-price-api `
    -p 8000:8000 `
    -e SCRAPER_API_KEY=$env:SCRAPER_API_KEY `
    store-price-api:latest

Write-Host "Container started successfully!"
Write-Host "API is available at http://localhost:8000"
Write-Host "To view logs: docker logs store-price-api"
Write-Host "To stop container: docker stop store-price-api" 