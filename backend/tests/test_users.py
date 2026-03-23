"""
User endpoint tests
Tests: search users, update profile, upload avatar
"""
import pytest
import requests
import os
import base64

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token(api_client, test_user_credentials):
    """Get auth token for test user"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        }
    )
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Auth token not available")

@pytest.fixture(scope="module")
def auth_token2(api_client, test_user2_credentials):
    """Get auth token for second test user"""
    # Create second user
    signup_response = api_client.post(
        f"{BASE_URL}/api/auth/signup",
        json=test_user2_credentials
    )
    if signup_response.status_code == 200:
        return signup_response.json()["token"]
    pytest.skip("Second user creation failed")

class TestUsers:
    """User management tests"""

    def test_search_users_empty_query(self, api_client, auth_token):
        """Test search with empty query"""
        response = api_client.get(
            f"{BASE_URL}/api/users/search?q=",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert data["users"] == []
        print("✓ Empty search query returns empty list")

    def test_search_users_by_username(self, api_client, auth_token, test_user2_credentials):
        """Test search users by username"""
        response = api_client.get(
            f"{BASE_URL}/api/users/search?q={test_user2_credentials['username'][:5]}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert len(data["users"]) > 0
        # Verify user found
        found = any(u["username"] == test_user2_credentials["username"] for u in data["users"])
        assert found, f"User {test_user2_credentials['username']} not found in search results"
        print(f"✓ Search found user by username")

    def test_search_users_by_email(self, api_client, auth_token, test_user2_credentials):
        """Test search users by email"""
        response = api_client.get(
            f"{BASE_URL}/api/users/search?q={test_user2_credentials['email'][:10]}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        print(f"✓ Search by email successful")

    def test_search_users_excludes_self(self, api_client, auth_token, test_user_credentials):
        """Test that search results exclude current user"""
        response = api_client.get(
            f"{BASE_URL}/api/users/search?q={test_user_credentials['username'][:5]}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Current user should not be in results
        found_self = any(u["username"] == test_user_credentials["username"] for u in data["users"])
        assert not found_self, "Search results should not include current user"
        print("✓ Search excludes current user")

    def test_search_users_unauthenticated(self, api_client):
        """Test search without authentication"""
        response = api_client.get(f"{BASE_URL}/api/users/search?q=test")
        assert response.status_code == 401
        print("✓ Unauthenticated search rejected")

    def test_update_profile_username(self, api_client, auth_token):
        """Test updating username"""
        import time
        new_username = f"updated_user_{int(time.time())}"
        
        response = api_client.put(
            f"{BASE_URL}/api/users/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"username": new_username}
        )
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert data["user"]["username"] == new_username
        
        # Verify persistence with GET /api/auth/me
        me_response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["user"]["username"] == new_username
        print(f"✓ Username updated to {new_username}")

    def test_update_profile_duplicate_username(self, api_client, auth_token, test_user2_credentials):
        """Test updating to an already taken username"""
        response = api_client.put(
            f"{BASE_URL}/api/users/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"username": test_user2_credentials["username"]}
        )
        assert response.status_code == 400
        data = response.json()
        assert "already taken" in data["detail"].lower()
        print("✓ Duplicate username rejected")

    def test_upload_avatar_base64(self, api_client, auth_token):
        """Test avatar upload with base64 data"""
        # Create a small test image (1x1 red pixel PNG)
        test_image_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        
        response = api_client.post(
            f"{BASE_URL}/api/users/avatar",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"avatar": test_image_base64}
        )
        assert response.status_code == 200
        data = response.json()
        assert "avatar" in data
        assert data["avatar"] == test_image_base64
        
        # Verify persistence
        me_response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["user"]["avatar"] == test_image_base64
        print("✓ Avatar uploaded successfully")

    def test_upload_avatar_missing_data(self, api_client, auth_token):
        """Test avatar upload without data"""
        response = api_client.post(
            f"{BASE_URL}/api/users/avatar",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={}
        )
        assert response.status_code == 400
        print("✓ Missing avatar data rejected")
