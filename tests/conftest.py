import pytest
import os
import sys
from pathlib import Path

# Add the application root directory to the Python path
root_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, root_dir)

# Set testing environment variable
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

# Clean up test database after tests
@pytest.fixture(autouse=True)
def cleanup_test_db():
    yield
    test_db = Path("test.db")
    if test_db.exists():
        test_db.unlink() 