import boto3
import time
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError
import logging
import stat
import subprocess
import sys

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class EC2Deployer:
    def __init__(self):
        self.ec2_client = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name='us-east-1'  # Change this to your preferred region
        )
        self.ec2_resource = boto3.resource(
            'ec2',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name='us-east-1'
        )

    def check_prerequisites(self):
        """Check if all prerequisites are met before deployment"""
        try:
            # Debug: Print current PATH
            current_path = os.environ.get('PATH', '')
            logger.info("Current PATH entries:")
            for path in current_path.split(';'):
                if path.strip():
                    logger.info(f"  - {path}")

            # Common PuTTY installation paths on Windows
            putty_paths = [
                r"C:\Program Files\PuTTY",
                r"C:\Program Files (x86)\PuTTY",
                os.path.expanduser("~\\AppData\\Local\\Programs\\PuTTY"),
                "."  # Current directory
            ]
            
            # Debug: Check each potential PuTTY path
            logger.info("Checking PuTTY paths:")
            for putty_path in putty_paths:
                if os.path.exists(putty_path):
                    logger.info(f"  Found directory: {putty_path}")
                    putty_exe = os.path.join(putty_path, "putty.exe")
                    puttygen_exe = os.path.join(putty_path, "puttygen.exe")
                    if os.path.exists(putty_exe):
                        logger.info(f"  Found putty.exe at: {putty_exe}")
                    if os.path.exists(puttygen_exe):
                        logger.info(f"  Found puttygen.exe at: {puttygen_exe}")
            
            # Try to find PuTTY executables in PATH using where command
            try:
                where_putty = subprocess.run(['where', 'putty.exe'], 
                                          capture_output=True, 
                                          text=True, 
                                          check=True)
                logger.info(f"PuTTY found by 'where' command at: {where_putty.stdout.strip()}")
            except subprocess.CalledProcessError:
                logger.warning("Could not find putty.exe using 'where' command")

            # Add PuTTY paths to system PATH temporarily
            original_path = os.environ.get('PATH', '')
            for putty_path in putty_paths:
                if os.path.exists(putty_path):
                    os.environ['PATH'] = f"{putty_path};{original_path}"
                    logger.info(f"Added to PATH: {putty_path}")
            
            # Check if PuTTY is installed and in PATH
            putty_found = False
            try:
                # Use PowerShell to check PuTTY version
                ps_command = "(Get-Item (Get-Command putty).Source).VersionInfo.FileVersion"
                putty_version = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if putty_version.stdout.strip():
                    logger.info(f"PuTTY is installed: version {putty_version.stdout.strip()}")
                    putty_found = True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.debug(f"Failed to get PuTTY version: {str(e)}")
            
            if not putty_found:
                logger.error("""
PuTTY is not found in PATH. Please try these troubleshooting steps:
1. Verify PuTTY is installed:
   - Open PowerShell and run: (Get-Item (Get-Command putty).Source).VersionInfo.FileVersion
   - If this fails, PuTTY is not in PATH

2. If PuTTY is installed but not found:
   a) Find your PuTTY installation directory
   b) Open System Properties (Win + Pause/Break)
   c) Click 'Environment Variables'
   d) Under System Variables, find and select 'Path'
   e) Click 'Edit'
   f) Verify the PuTTY directory is listed
   g) If not, add it and click 'OK'

3. Alternative installation:
   - Download PuTTY from https://www.putty.org/
   - Run the installer as Administrator
   - Choose 'Add to PATH' during installation

4. After making changes:
   - Close and reopen PowerShell
   - Try running the version check command again

Current checked locations:
""")
                for path in putty_paths:
                    logger.error(f"  - {path}")
                return False

            # Check if puttygen is available
            puttygen_found = False
            try:
                # Use PowerShell to check PuTTYgen version
                ps_command = "(Get-Item (Get-Command puttygen).Source).VersionInfo.FileVersion"
                puttygen_version = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if puttygen_version.stdout.strip():
                    logger.info(f"PuTTYgen is installed: version {puttygen_version.stdout.strip()}")
                    puttygen_found = True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.debug(f"Failed to get PuTTYgen version: {str(e)}")
            
            if not puttygen_found:
                logger.error("PuTTYgen is not found. It should have been installed with PuTTY.")
                return False

            # Check AWS credentials
            if not all([os.getenv('AWS_ACCESS_KEY_ID'), 
                       os.getenv('AWS_SECRET_ACCESS_KEY')]):
                logger.error("AWS credentials are not properly configured in .env file")
                return False

            # Check if SCRAPER_API_KEY exists
            if not os.getenv('SCRAPER_API_KEY'):
                logger.error("SCRAPER_API_KEY is not set in .env file")
                return False

            logger.info("All prerequisites are met!")
            return True

        except Exception as e:
            logger.error(f"Error checking prerequisites: {str(e)}")
            return False

    def terminate_previous_instances(self):
        """Terminate any existing instances with the PriceScraper tag"""
        try:
            instances = self.ec2_resource.instances.filter(
                Filters=[
                    {'Name': 'tag:Name', 'Values': ['PriceScraper']},
                    {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping', 'stopped']}
                ]
            )
            
            terminated = False
            for instance in instances:
                logger.info(f"Terminating previous instance: {instance.id}")
                instance.terminate()
                terminated = True
            
            if terminated:
                # Wait for instances to terminate
                logger.info("Waiting for instances to terminate...")
                waiter = self.ec2_client.get_waiter('instance_terminated')
                waiter.wait(
                    Filters=[
                        {'Name': 'tag:Name', 'Values': ['PriceScraper']},
                    ]
                )
                logger.info("Previous instances terminated successfully")
            
            return terminated
        except Exception as e:
            logger.error(f"Error terminating previous instances: {str(e)}")
            raise

    def cleanup_key_pairs(self, key_name='price-scraper-key'):
        """Remove existing key pair if it exists"""
        try:
            # Delete the key pair from AWS first
            try:
                self.ec2_client.delete_key_pair(KeyName=key_name)
            except ClientError as e:
                if 'NotFound' not in str(e):
                    raise

            # Try to remove local .pem and .ppk files if they exist
            pem_file = f"{key_name}.pem"
            ppk_file = f"{key_name}.ppk"
            
            for file_path in [pem_file, ppk_file]:
                if os.path.exists(file_path):
                    try:
                        os.chmod(file_path, stat.S_IWRITE)
                        os.remove(file_path)
                        logger.info(f"Cleaned up existing key file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Could not remove local key file {file_path}. You may need to delete it manually. Error: {str(e)}")
                        pass
        except Exception as e:
            logger.error(f"Error during key pair cleanup: {str(e)}")
            raise

    def create_key_pair(self, key_name='price-scraper-key'):
        """Create a key pair for SSH access"""
        try:
            key_pair = self.ec2_client.create_key_pair(KeyName=key_name)
            # Save private key to file
            with open(f"{key_name}.pem", 'w') as file:
                file.write(key_pair['KeyMaterial'])
            os.chmod(f"{key_name}.pem", 0o400)  # Set correct permissions
            print(f"Created key pair: {key_name}")
            return key_name
        except ClientError as e:
            if 'KeyPair already exists' in str(e):
                print(f"Key pair {key_name} already exists")
                return key_name
            raise

    def create_security_group(self, group_name='price-scraper-sg'):
        """Create a security group with necessary ports"""
        try:
            security_group = self.ec2_client.create_security_group(
                GroupName=group_name,
                Description='Security group for Price Scraper application'
            )
            security_group_id = security_group['GroupId']

            # Add inbound rules
            self.ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )
            print(f"Created security group: {group_name}")
            return security_group_id
        except ClientError as e:
            if 'already exists' in str(e):
                print(f"Security group {group_name} already exists")
                return self.ec2_client.describe_security_groups(
                    GroupNames=[group_name]
                )['SecurityGroups'][0]['GroupId']
            raise

    def create_instance(self, key_name, security_group_id):
        """Create EC2 instance"""
        # Ubuntu 22.04 LTS AMI ID (us-east-1)
        ami_id = 'ami-0c7217cdde317cfec'

        # Set a default password for the ubuntu user
        password = 'PriceScraper2024!'
        
        user_data = '''#!/bin/bash
# Update system and install required packages
apt-get update
apt-get install -y python3-pip python3-venv git nginx

# Set password for ubuntu user
echo "ubuntu:''' + password + '''" | chpasswd
sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
systemctl restart sshd

# Clone repository and setup application
cd /home/ubuntu
rm -rf app
git clone https://github.com/hoaglandl/PriceScraping.git app || {
    echo "Failed to clone repository"
    exit 1
}
chown -R ubuntu:ubuntu /home/ubuntu/app

# Create .env file
cat > /home/ubuntu/app/.env << EOL
SCRAPER_API_KEY=''' + os.getenv('SCRAPER_API_KEY') + '''
AWS_ACCESS_KEY_ID=''' + os.getenv('AWS_ACCESS_KEY_ID') + '''
AWS_SECRET_ACCESS_KEY=''' + os.getenv('AWS_SECRET_ACCESS_KEY') + '''
EOL

# Setup Python environment and install dependencies
cd /home/ubuntu/app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt || {
    echo "Failed to install requirements"
    exit 1
}

# Setup systemd service
cat > /etc/systemd/system/pricescraper.service << EOL
[Unit]
Description=Price Scraper FastAPI Application
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/app
Environment="PATH=/home/ubuntu/app/venv/bin"
ExecStart=/home/ubuntu/app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

[Install]
WantedBy=multi-user.target
EOL

# Configure Nginx
cat > /etc/nginx/sites-available/pricescraper << 'EOL'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
EOL

# Enable the Nginx site and restart services
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/pricescraper /etc/nginx/sites-enabled/
systemctl daemon-reload
systemctl enable nginx
systemctl enable pricescraper
systemctl restart nginx
systemctl restart pricescraper

# Check service status
systemctl status pricescraper --no-pager
systemctl status nginx --no-pager
'''

        instance = self.ec2_resource.create_instances(
            ImageId=ami_id,
            InstanceType='t2.micro',
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            MinCount=1,
            MaxCount=1,
            UserData=user_data,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': 'PriceScraper'
                        }
                    ]
                }
            ]
        )[0]

        print(f"Created instance: {instance.id}")
        return instance

    def wait_for_instance(self, instance):
        """Wait for instance to be running and get its public IP"""
        instance.wait_until_running()
        instance.reload()  # Reload instance attributes
        return instance.public_ip_address

    def convert_to_ppk(self, key_name='price-scraper-key'):
        """Convert .pem key to .ppk format for PuTTY"""
        try:
            pem_file = f"{key_name}.pem"
            ppk_file = f"{key_name}.ppk"
            
            # Common PuTTY installation paths on Windows
            putty_paths = [
                r"C:\Program Files\PuTTY",
                r"C:\Program Files (x86)\PuTTY",
            ]
            
            # Add PuTTY paths to system PATH temporarily
            original_path = os.environ.get('PATH', '')
            for putty_path in putty_paths:
                if os.path.exists(putty_path):
                    os.environ['PATH'] = f"{putty_path};{original_path}"
                    break
            
            # Convert key using puttygen with correct parameters
            try:
                # First, ensure the .pem file has the right permissions
                os.chmod(pem_file, 0o600)
                
                # Convert using puttygen
                convert_cmd = [
                    'puttygen.exe',
                    pem_file,
                    '-O', 'private',
                    '-o', ppk_file
                ]
                result = subprocess.run(
                    convert_cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                if os.path.exists(ppk_file):
                    logger.info(f"Successfully converted {pem_file} to {ppk_file}")
                    return True
                else:
                    logger.error("PPK file was not created despite successful command execution")
                    return False
                    
            except subprocess.CalledProcessError as e:
                logger.error(f"Error converting key to PPK format: {str(e)}")
                logger.error(f"Command output: {e.stdout}")
                logger.error(f"Command error: {e.stderr}")
                logger.info("You can manually convert the key using these steps:")
                logger.info("1. Open PuTTYgen")
                logger.info("2. Click 'Load' and select the .pem file")
                logger.info("3. Click 'Save private key' and save as .ppk")
                return False
            except FileNotFoundError:
                logger.error("puttygen.exe not found. Please ensure PuTTY is installed correctly.")
                return False
        except Exception as e:
            logger.error(f"Error during key conversion: {str(e)}")
            return False

    def deploy(self):
        """Main deployment method"""
        try:
            logger.info("Checking prerequisites...")
            if not self.check_prerequisites():
                logger.error("Prerequisites check failed. Please fix the issues above and try again.")
                return None

            logger.info("Starting deployment...")
            
            # Terminate any existing instances
            self.terminate_previous_instances()
            
            # Cleanup and create new key pair
            self.cleanup_key_pairs()
            key_name = self.create_key_pair()
            
            # Convert key to PPK format for PuTTY
            ppk_success = self.convert_to_ppk(key_name)
            
            # Create security group
            security_group_id = self.create_security_group()
            
            # Create EC2 instance
            instance = self.create_instance(key_name, security_group_id)
            
            # Wait for instance to be ready
            public_ip = self.wait_for_instance(instance)
            
            logger.info("\nDeployment completed successfully!")
            logger.info(f"Public IP: {public_ip}")
            if ppk_success:
                logger.info("\nTo connect using PuTTY:")
                logger.info(f"1. Open PuTTY")
                logger.info(f"2. Set the hostname to: ubuntu@{public_ip}")
                logger.info(f"3. Go to Connection > SSH > Auth > Credentials")
                logger.info(f"4. Browse and select the private key file: {key_name}.ppk")
                logger.info(f"5. Click Open to connect")
                logger.info(f"\nApplication will be available at: http://{public_ip}")
                logger.info("It may take 5-10 minutes for the application to be fully deployed.")
            else:
                logger.warning("\nPPK conversion failed. You'll need to manually convert the .pem file using PuTTYgen")
                logger.info(f"PEM file location: {key_name}.pem")
            
            logger.info("\nNote: Wait a few minutes for the instance to complete its setup")
            
            return public_ip
            
        except Exception as e:
            logger.error(f"Error during deployment: {str(e)}")
            raise

if __name__ == "__main__":
    try:
        deployer = EC2Deployer()
        public_ip = deployer.deploy()
        if public_ip:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}")
        sys.exit(1) 