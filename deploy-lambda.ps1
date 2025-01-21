# Script to deploy to AWS Lambda using AWS CLI directly
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

# Check prerequisites
if (-not (Check-Docker)) { exit 1 }
$AWS_ACCOUNT_ID = Check-AWS
if (-not $AWS_ACCOUNT_ID) { exit 1 }

# Load environment variables
Write-Host "Loading environment variables..."
Load-EnvFile

# Set variables
$REGION = "us-east-1"
$FUNCTION_NAME = "store-price-api"
$ECR_REPO = "${FUNCTION_NAME}-dev"
$IMAGE_URI = "${AWS_ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
$ROLE_NAME = "${FUNCTION_NAME}-lambda-role"
$ROLE_ARN = "arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"

# Clean up Docker system
Write-Host "Cleaning Docker system..."
docker system prune -af

# Create IAM role if it doesn't exist
Write-Host "Creating/checking IAM role..."
aws iam get-role --role-name $ROLE_NAME 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating IAM role..."
    
    # Create trust policy
    $trustPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    
    # Create role
    Write-Host "Creating role..."
    aws iam create-role --role-name $ROLE_NAME --assume-role-policy-document $trustPolicy | Out-Null
    
    # Attach policy
    Write-Host "Attaching execution policy..."
    aws iam attach-role-policy --role-name $ROLE_NAME --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    
    # Wait for role to be available
    Write-Host "Waiting for role to be available..."
    Start-Sleep -Seconds 10
}

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

# Check if Lambda function exists
Write-Host "Checking if Lambda function exists..."
aws lambda get-function --function-name $FUNCTION_NAME 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    # Update existing function
    Write-Host "Updating existing Lambda function..."
    aws lambda update-function-code `
        --function-name $FUNCTION_NAME `
        --image-uri "${IMAGE_URI}:latest"
} else {
    # Create new function
    Write-Host "Creating new Lambda function..."
    aws lambda create-function `
        --function-name $FUNCTION_NAME `
        --package-type Image `
        --code ImageUri="${IMAGE_URI}:latest" `
        --role $ROLE_ARN `
        --timeout 29 `
        --memory-size 512 `
        --environment "Variables={SCRAPER_API_KEY=$env:SCRAPER_API_KEY}"
}

Write-Host "Deployment completed!" 