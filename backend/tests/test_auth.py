"""
Authentication endpoint tests
Tests: signup, login, me, logout
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication flow tests"""

    def test_health_check(self, api_client):
        """Test API health endpoint"""
        response = api_client.get(f"{BASE_URL}/api")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["status"] == "online"
        print("✓ Health check passed")

    def test_signup_success(self, api_client, test_user_credentials):
        """Test user signup with valid credentials"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json=test_user_credentials
        )
        assert response.status_code == 200, f"Signup failed: {response.text}"
        
        data = response.json()
        assert "token" in data, "Token missing in signup response"
        assert "user" in data, "User missing in signup response"
        assert data["user"]["email"] == test_user_credentials["email"]
        assert data["user"]["username"] == test_user_credentials["username"]
        assert "user_id" in data["user"]
        assert "password_hash" not in data["user"], "Password hash exposed in response"
        print(f"✓ Signup successful for {test_user_credentials['email']}")

    def test_signup_duplicate_email(self, api_client, test_user_credentials):
        """Test signup with already registered email"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json=test_user_credentials
        )
        assert response.status_code == 400
        data = response.json()
        assert "already registered" in data["detail"].lower()
        print("✓ Duplicate email rejected")

    def test_login_success(self, api_client, test_user_credentials):
        """Test login with valid credentials"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == test_user_credentials["email"]
        print(f"✓ Login successful for {test_user_credentials['email']}")

    def test_login_invalid_credentials(self, api_client, test_user_credentials):
        """Test login with wrong password"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": "WrongPassword123!"
            }
        )
        assert response.status_code == 401
        data = response.json()
        assert "invalid credentials" in data["detail"].lower()
        print("✓ Invalid credentials rejected")

    def test_login_nonexistent_user(self, api_client):
        """Test login with non-existent email"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "SomePassword123!"
            }
        )
        assert response.status_code == 401
        print("✓ Non-existent user rejected")

    def test_get_me_authenticated(self, api_client, test_user_credentials):
        """Test GET /api/auth/me with valid token"""
        # First login to get token
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]
        
        # Test /me endpoint
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert data["user"]["email"] == test_user_credentials["email"]
        print("✓ GET /api/auth/me successful")

    def test_get_me_unauthenticated(self, api_client):
        """Test GET /api/auth/me without token"""
        response = api_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("✓ Unauthenticated request rejected")

    def test_get_me_invalid_token(self, api_client):
        """Test GET /api/auth/me with invalid token"""
        response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        assert response.status_code == 401
        print("✓ Invalid token rejected")

    def test_logout(self, api_client, test_user_credentials):
        """Test POST /api/auth/logout"""
        # Login first
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        # Logout
        response = api_client.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print("✓ Logout successful")
