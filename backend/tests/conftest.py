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
    """Use existing test user credentials."""
    return {
        "email": "geo_test@test.com",
        "username": "geo_test",
        "password": "pass1234"
    }

@pytest.fixture(scope="session")
def test_user2_credentials():
    """Use existing second test user credentials."""
    return {
        "email": "geo_nearby@test.com",
        "username": "geo_nearby",
        "password": "pass1234"
    }
