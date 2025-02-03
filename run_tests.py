import subprocess
import time
import os
import sys
import requests
import signal
from app.core.config import get_settings

def is_server_running(url: str = "http://localhost:8000/health") -> bool:
    try:
        response = requests.get(url)
        return response.status_code == 200
    except requests.ConnectionError:
        return False

def main():
    # Load settings
    settings = get_settings()
    
    # Get the absolute path to the virtual environment's Python
    venv_path = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_path):
        print("Error: Virtual environment not found!")
        sys.exit(1)

    # Environment setup with configuration
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": os.getcwd(),
        "DEBUG": "1",
        "RELOAD": "true",
        "SCRAPER_API_KEY": settings.scraper_api_key,
        "API_TIMEOUT": str(settings.api_timeout),
        "MAX_RETRIES": str(settings.max_retries),
        "MAX_URLS_PER_REQUEST": str(settings.max_urls_per_request)
    })

    # Start the FastAPI server
    server_process = subprocess.Popen(
        [venv_path, "run.py"],
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )

    print("Starting FastAPI server...")
    
    # Wait for the server to start
    max_attempts = settings.max_retries
    attempt = 0
    while not is_server_running() and attempt < max_attempts:
        time.sleep(1)
        attempt += 1
        print(".", end="", flush=True)
    
    print("\n")
    
    if not is_server_running():
        print("Error: Server failed to start!")
        server_process.terminate()
        sys.exit(1)

    print("Server is running!")

    try:
        # Run the tests
        print("\nRunning tests...")
        test_result = subprocess.run(
            [venv_path, "-m", "pytest", "tests/test_api.py", "-v"],
            check=True,
            env=env
        )

    except subprocess.CalledProcessError as e:
        print(f"Tests failed with exit code: {e.returncode}")
    except KeyboardInterrupt:
        print("\nInterrupted by user. Shutting down...")
    finally:
        # Cleanup: Stop the server
        print("\nStopping server...")
        server_process.send_signal(signal.CTRL_BREAK_EVENT)
        server_process.terminate()
        server_process.wait(timeout=settings.api_timeout)
        print("Server stopped!")

if __name__ == "__main__":
    main() 