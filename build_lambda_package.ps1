# Create a temporary directory for building
New-Item -ItemType Directory -Force -Path .\build

# Copy application files
Copy-Item -Path .\app -Destination .\build\app -Recurse
Copy-Item -Path .\lambda_handler.py -Destination .\build\
Copy-Item -Path .\requirements.txt -Destination .\build\

# Use docker to install dependencies in a Lambda-like environment
docker run --rm -v ${PWD}/build:/var/task public.ecr.aws/sam/build-python3.9:latest pip install -r /var/task/requirements.txt -t /var/task/

# Create deployment package
Compress-Archive -Path .\build\* -DestinationPath .\function.zip -Force

# Clean up
Remove-Item -Path .\build -Recurse -Force

Write-Host "Deployment package created as function.zip" 