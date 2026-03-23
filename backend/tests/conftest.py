import pytest
import requests
import os

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="session")
def api_client():
    """Shared requests session for all tests."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="session")
def test_user_credentials():
    """Generate unique test user credentials."""
    import time
    timestamp = int(time.time() * 1000)
    return {
        "email": f"test_user_{timestamp}@example.com",
        "username": f"testuser_{timestamp}",
        "password": "TestPass123!"
    }

@pytest.fixture(scope="session")
def test_user2_credentials():
    """Generate second test user credentials for multi-user tests."""
    import time
    timestamp = int(time.time() * 1000) + 1
    return {
        "email": f"test_user2_{timestamp}@example.com",
        "username": f"testuser2_{timestamp}",
        "password": "TestPass456!"
    }
