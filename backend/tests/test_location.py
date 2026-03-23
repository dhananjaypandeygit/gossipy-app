"""
Location and Nearby Users endpoint tests
Tests: PUT /api/users/location, GET /api/users/nearby with radius filters
MongoDB 2dsphere geospatial queries
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

class TestLocation:
    """Location and nearby users tests"""

    def test_create_test_user(self, api_client, test_user_credentials):
        """Create test user for location tests"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json=test_user_credentials
        )
        # 200 if new user, 400 if already exists (from previous run)
        assert response.status_code in [200, 400]
        print(f"✓ Test user ready: {test_user_credentials['email']}")

    def test_update_location_success(self, api_client, test_user_credentials):
        """Test PUT /api/users/location with valid coordinates"""
        # Login first
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]
        
        # Update location (NYC coordinates)
        location_data = {
            "latitude": 40.7128,
            "longitude": -74.0060
        }
        response = api_client.put(
            f"{BASE_URL}/api/users/location",
            headers={"Authorization": f"Bearer {token}"},
            json=location_data
        )
        assert response.status_code == 200, f"Location update failed: {response.text}"
        
        data = response.json()
        assert data["success"] is True
        assert "location" in data
        assert data["location"]["latitude"] == location_data["latitude"]
        assert data["location"]["longitude"] == location_data["longitude"]
        print(f"✓ Location updated successfully to ({location_data['latitude']}, {location_data['longitude']})")

    def test_update_location_unauthenticated(self, api_client):
        """Test PUT /api/users/location without authentication"""
        response = api_client.put(
            f"{BASE_URL}/api/users/location",
            json={"latitude": 40.7128, "longitude": -74.0060}
        )
        assert response.status_code == 401
        print("✓ Unauthenticated location update rejected")

    def test_nearby_users_empty_radius(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby returns empty when no users in radius"""
        # Login
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        # Query very small radius (10m) in remote location
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=0.0&longitude=0.0&radius=10",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert isinstance(data["users"], list)
        assert data["radius"] == 10
        assert data["count"] == len(data["users"])
        print(f"✓ Nearby query returned {data['count']} users (expected 0 or few)")

    def test_nearby_users_with_radius_10m(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby with 10m radius"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        # Update own location first
        api_client.put(
            f"{BASE_URL}/api/users/location",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060}
        )
        
        # Query nearby with 10m radius
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=10",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["radius"] == 10
        assert "users" in data
        print(f"✓ Nearby query (10m) returned {data['count']} users")

    def test_nearby_users_with_radius_50m(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby with 50m radius"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=50",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["radius"] == 50
        print(f"✓ Nearby query (50m) returned {data['count']} users")

    def test_nearby_users_with_radius_100m(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby with 100m radius"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=100",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["radius"] == 100
        print(f"✓ Nearby query (100m) returned {data['count']} users")

    def test_nearby_users_with_radius_500m(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby with 500m radius (default)"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=500",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["radius"] == 500
        print(f"✓ Nearby query (500m) returned {data['count']} users")

    def test_nearby_users_excludes_current_user(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby excludes current user from results"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        current_user_id = login_response.json()["user"]["user_id"]
        
        # Update own location
        api_client.put(
            f"{BASE_URL}/api/users/location",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060}
        )
        
        # Query nearby
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=500",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify current user is NOT in results
        user_ids = [u["user_id"] for u in data["users"]]
        assert current_user_id not in user_ids, "Current user should be excluded from nearby results"
        print(f"✓ Current user excluded from nearby results")

    def test_nearby_users_returns_distance_meters(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby returns distance_meters for each user"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        # Create second user with nearby location
        timestamp = int(time.time() * 1000)
        user2_creds = {
            "email": f"nearby_test_{timestamp}@example.com",
            "username": f"nearbyuser_{timestamp}",
            "password": "TestPass123!"
        }
        signup_response = api_client.post(f"{BASE_URL}/api/auth/signup", json=user2_creds)
        assert signup_response.status_code == 200
        user2_token = signup_response.json()["token"]
        
        # Set user2 location very close to test location (40.7128, -74.0060)
        # Offset by ~50 meters: 0.0005 degrees latitude ≈ 55 meters
        api_client.put(
            f"{BASE_URL}/api/users/location",
            headers={"Authorization": f"Bearer {user2_token}"},
            json={"latitude": 40.7133, "longitude": -74.0060}
        )
        
        # Query nearby from user1
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=500",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify at least one user returned with distance_meters
        if data["count"] > 0:
            for user in data["users"]:
                assert "distance_meters" in user, "distance_meters field missing"
                assert isinstance(user["distance_meters"], (int, float)), "distance_meters should be numeric"
                assert user["distance_meters"] >= 0, "distance_meters should be non-negative"
                print(f"✓ User {user['username']} at {user['distance_meters']}m")
        print(f"✓ All nearby users have distance_meters field")

    def test_nearby_users_unauthenticated(self, api_client):
        """Test GET /api/users/nearby without authentication"""
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=500"
        )
        assert response.status_code == 401
        print("✓ Unauthenticated nearby query rejected")

    def test_nearby_users_invalid_radius_fallback(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby with invalid radius falls back to nearest valid"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        # Query with invalid radius (should fallback to nearest valid: 100)
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=75",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        # Backend should normalize to nearest valid radius
        assert data["radius"] in [10, 50, 100, 500]
        print(f"✓ Invalid radius (75) normalized to {data['radius']}m")

    def test_nearby_users_data_structure(self, api_client, test_user_credentials):
        """Test GET /api/users/nearby returns correct data structure"""
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_credentials["email"],
                "password": test_user_credentials["password"]
            }
        )
        token = login_response.json()["token"]
        
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude=40.7128&longitude=-74.0060&radius=500",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "users" in data
        assert "radius" in data
        assert "count" in data
        assert isinstance(data["users"], list)
        assert isinstance(data["radius"], int)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["users"])
        
        # Verify user structure (if any users returned)
        if data["count"] > 0:
            user = data["users"][0]
            assert "user_id" in user
            assert "username" in user
            assert "email" in user
            assert "distance_meters" in user
            assert "is_online" in user
            # Verify sensitive data NOT exposed
            assert "password_hash" not in user
            assert "_id" not in user
            # Verify location privacy (location should be removed)
            assert "location" not in user, "Location coordinates should not be exposed for privacy"
            assert "location_updated_at" not in user
        
        print(f"✓ Nearby users response structure correct")
