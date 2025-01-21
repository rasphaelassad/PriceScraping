# Script to clean up all Serverless Framework resources

Write-Host "Cleaning up AWS resources..."

# Delete CloudFormation stack
Write-Host "Deleting CloudFormation stack..."
aws cloudformation delete-stack --stack-name store-price-api-dev

# Wait for stack deletion to complete
Write-Host "Waiting for stack deletion..."
aws cloudformation wait stack-delete-complete --stack-name store-price-api-dev

# Delete ECR repository
Write-Host "Deleting ECR repository..."
aws ecr delete-repository --repository-name store-price-api-dev --force

# Clean up local files
Write-Host "Cleaning up local files..."
Remove-Item -Path .serverless -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path node_modules -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path package-lock.json -Force -ErrorAction SilentlyContinue

# Clean up Docker
Write-Host "Cleaning up Docker..."
docker rm -f $(docker ps -aq) 2>$null
docker rmi -f $(docker images -q) 2>$null
docker system prune -af

Write-Host "Cleanup completed!" 