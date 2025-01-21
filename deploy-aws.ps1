# Script to deploy to AWS Lambda using Serverless Framework
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

# Check Docker is running
function Check-Docker {
    try {
        docker info > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker is running"
            return $true
        }
    } catch {}
    
    Write-Host "Error: Docker is not running. Please start Docker Desktop and try again."
    return $false
}

# Check AWS credentials
function Check-AWS {
    try {
        $identity = aws sts get-caller-identity | ConvertFrom-Json
        if ($LASTEXITCODE -eq 0) {
            Write-Host "AWS credentials are configured"
            return $identity.Account
        }
    } catch {}
    
    Write-Host "Error: AWS credentials not found. Please run 'aws configure' first."
    return $false
}

# Check if Serverless Framework is installed
if (-not (Get-Command serverless -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Serverless Framework..."
    npm install -g serverless
}

# Check prerequisites
if (-not (Check-Docker)) { exit 1 }
$AWS_ACCOUNT_ID = Check-AWS
if (-not $AWS_ACCOUNT_ID) { exit 1 }

# Load environment variables
Write-Host "Loading environment variables..."
Load-EnvFile

# Set variables
$REGION = "us-east-1"
$ECR_REPO = "store-price-api-dev"
$IMAGE_URI = "${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

# Clean up Docker system
Write-Host "Cleaning Docker system..."
docker system prune -af

# Create ECR repository if it doesn't exist
Write-Host "Creating/checking ECR repository..."
aws ecr describe-repositories --repository-names ${ECR_REPO} 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating ECR repository..."
    aws ecr create-repository --repository-name ${ECR_REPO} | Out-Null
}

# Log in to ECR
Write-Host "Logging in to ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Build Docker image
Write-Host "Building Docker image..."
docker build -t ${ECR_REPO}:latest -f Dockerfile.lambda .

# Tag and push image
Write-Host "Tagging and pushing image..."
docker tag ${ECR_REPO}:latest ${IMAGE_URI}:latest
docker push ${IMAGE_URI}:latest

# Wait for image to be available
Write-Host "Waiting for image to be available in ECR..."
Start-Sleep -Seconds 15

# Deploy using Serverless Framework
Write-Host "Deploying to AWS Lambda..."
serverless deploy --verbose

Write-Host "Deployment completed!" 