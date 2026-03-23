"""
Proximity Chat endpoint tests
Tests: POST /api/proximity/join, POST /api/proximity/leave, GET /api/proximity/room/{room_id}
      GET /api/proximity/messages/{room_id}, POST /api/proximity/messages
      GeoHash encoding, room ID generation, TTL index verification
"""
import pytest
import requests
import os
import time
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

# Load backend .env
load_dotenv(Path(__file__).parent.parent / '.env')

# Use frontend .env for BACKEND_URL
frontend_env = Path(__file__).parent.parent.parent / 'frontend' / '.env'
if frontend_env.exists():
    with open(frontend_env) as f:
        for line in f:
            if line.startswith('EXPO_PUBLIC_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().strip('"').rstrip('/')
                break
else:
    BASE_URL = ''

MONGO_URL = os.environ.get('MONGO_URL', '')
DB_NAME = os.environ.get('DB_NAME', '')

class TestProximityChat:
    """Proximity chat room and messaging tests"""

    def test_verify_ttl_index_exists(self):
        """Verify MongoDB TTL index exists on proximity_messages.expires_at"""
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        indexes = list(db.proximity_messages.list_indexes())
        
        ttl_index_found = False
        for idx in indexes:
            if 'expires_at' in idx.get('key', {}):
                ttl_index_found = True
                assert idx.get('expireAfterSeconds') == 0, "TTL index should have expireAfterSeconds=0"
                print(f"✓ TTL index found on proximity_messages.expires_at with expireAfterSeconds=0")
                break
        
        assert ttl_index_found, "TTL index not found on proximity_messages.expires_at"
        client.close()

    def test_join_proximity_room_success(self, api_client):
        """Test POST /api/proximity/join - Join proximity room based on location+radius"""
        # Login with test user
        login_response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json()["token"]
        
        # Join proximity room
        join_data = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius": 500
        }
        response = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json=join_data
        )
        assert response.status_code == 200, f"Join proximity room failed: {response.text}"
        
        data = response.json()
        assert "room_id" in data
        assert "geohash" in data
        assert "radius" in data
        assert "participant_count" in data
        assert data["radius"] == 500
        assert data["room_id"].startswith("prox_")
        assert data["room_id"].endswith("_500m")
        print(f"✓ Joined proximity room: {data['room_id']} with {data['participant_count']} participants")

    def test_join_proximity_room_same_geohash(self, api_client):
        """Test POST /api/proximity/join - Two users at similar locations get same room_id"""
        # User 1 joins
        login1 = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token1 = login1.json()["token"]
        
        join1 = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token1}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id_1 = join1.json()["room_id"]
        
        # User 2 joins at same location
        login2 = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_nearby@test.com", "password": "pass1234"}
        )
        token2 = login2.json()["token"]
        
        join2 = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token2}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id_2 = join2.json()["room_id"]
        
        assert room_id_1 == room_id_2, "Users at same location should get same room_id"
        print(f"✓ Both users joined same room: {room_id_1}")

    def test_join_proximity_room_different_radius(self, api_client):
        """Test POST /api/proximity/join - Different radius creates different room_id"""
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        # Join with 500m radius
        join1 = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id_500 = join1.json()["room_id"]
        
        # Join with 100m radius (same location)
        join2 = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 100}
        )
        room_id_100 = join2.json()["room_id"]
        
        assert room_id_500 != room_id_100, "Different radius should create different room_id"
        assert "_500m" in room_id_500
        assert "_100m" in room_id_100
        print(f"✓ Different radius creates different rooms: {room_id_500} vs {room_id_100}")

    def test_geohash_precision_mapping(self, api_client):
        """Test GeoHash encoding produces correct room IDs for different precision levels"""
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        # Test all radius options
        radius_tests = [
            (10, 8),   # 10m -> precision 8
            (50, 7),   # 50m -> precision 7
            (100, 6),  # 100m -> precision 6
            (500, 5),  # 500m -> precision 5
        ]
        
        for radius, expected_precision in radius_tests:
            join = api_client.post(
                f"{BASE_URL}/api/proximity/join",
                headers={"Authorization": f"Bearer {token}"},
                json={"latitude": 40.7128, "longitude": -74.0060, "radius": radius}
            )
            assert join.status_code == 200
            data = join.json()
            geohash = data["geohash"]
            # Geohash length should match expected precision
            assert len(geohash) == expected_precision, f"Radius {radius}m should produce geohash precision {expected_precision}, got {len(geohash)}"
            print(f"✓ Radius {radius}m -> geohash precision {expected_precision}: {geohash}")

    def test_leave_proximity_room_success(self, api_client):
        """Test POST /api/proximity/leave - Leave proximity room"""
        # Login and join room
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        join = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join.json()["room_id"]
        initial_count = join.json()["participant_count"]
        
        # Leave room
        leave = api_client.post(
            f"{BASE_URL}/api/proximity/leave",
            headers={"Authorization": f"Bearer {token}"},
            json={"room_id": room_id}
        )
        assert leave.status_code == 200, f"Leave room failed: {leave.text}"
        
        data = leave.json()
        assert data["success"] is True
        assert "participant_count" in data
        # Count should be decremented (or 0 if we were the only one)
        assert data["participant_count"] < initial_count or data["participant_count"] == 0
        print(f"✓ Left room {room_id}, participant count: {initial_count} -> {data['participant_count']}")

    def test_get_proximity_room_info(self, api_client):
        """Test GET /api/proximity/room/{room_id} - Get room info with participants"""
        # Login and join room
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        join = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join.json()["room_id"]
        
        # Get room info
        response = api_client.get(
            f"{BASE_URL}/api/proximity/room/{room_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Get room info failed: {response.text}"
        
        data = response.json()
        assert "room" in data
        assert "participants" in data
        assert data["room"]["room_id"] == room_id
        assert "participant_count" in data["room"]
        assert isinstance(data["participants"], list)
        assert len(data["participants"]) == data["room"]["participant_count"]
        
        # Verify participant structure
        if len(data["participants"]) > 0:
            participant = data["participants"][0]
            assert "user_id" in participant
            assert "username" in participant
            assert "is_online" in participant
            assert "password_hash" not in participant
            assert "_id" not in participant
        
        print(f"✓ Room info retrieved: {room_id} with {data['room']['participant_count']} participants")

    def test_get_proximity_messages(self, api_client):
        """Test GET /api/proximity/messages/{room_id} - Get messages for a room"""
        # Use existing room with messages
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        # Join the existing room
        join = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join.json()["room_id"]
        
        # Get messages
        response = api_client.get(
            f"{BASE_URL}/api/proximity/messages/{room_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200, f"Get messages failed: {response.text}"
        
        data = response.json()
        assert "messages" in data
        assert isinstance(data["messages"], list)
        
        # Verify message structure if any messages exist
        if len(data["messages"]) > 0:
            msg = data["messages"][0]
            assert "message_id" in msg
            assert "room_id" in msg
            assert "sender_id" in msg
            assert "sender_username" in msg
            assert "content" in msg or "image" in msg
            assert "created_at" in msg
            assert "expires_at" in msg
            assert "_id" not in msg
        
        print(f"✓ Retrieved {len(data['messages'])} messages from room {room_id}")

    def test_send_proximity_message_success(self, api_client):
        """Test POST /api/proximity/messages - Send message to proximity room"""
        # Login and join room
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        join = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join.json()["room_id"]
        
        # Send message
        message_data = {
            "room_id": room_id,
            "content": f"Test proximity message at {int(time.time())}",
            "msg_type": "text"
        }
        response = api_client.post(
            f"{BASE_URL}/api/proximity/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=message_data
        )
        assert response.status_code == 200, f"Send message failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        msg = data["message"]
        assert msg["room_id"] == room_id
        assert msg["content"] == message_data["content"]
        assert "expires_at" in msg
        assert "sender_username" in msg
        assert "_id" not in msg
        
        print(f"✓ Message sent to room {room_id}: {msg['message_id']}")

    def test_send_proximity_message_non_participant(self, api_client):
        """Test POST /api/proximity/messages - Non-participant cannot send message (403)"""
        # Login but don't join any room
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        # Try to send message to a room we're not in
        # First, create a room with another user
        login2 = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_nearby@test.com", "password": "pass1234"}
        )
        token2 = login2.json()["token"]
        
        join = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token2}"},
            json={"latitude": 50.0, "longitude": 50.0, "radius": 500}  # Different location
        )
        room_id = join.json()["room_id"]
        
        # Now try to send message from user1 (not in this room)
        message_data = {
            "room_id": room_id,
            "content": "Unauthorized message",
            "msg_type": "text"
        }
        response = api_client.post(
            f"{BASE_URL}/api/proximity/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=message_data
        )
        assert response.status_code == 403, f"Expected 403 for non-participant, got {response.status_code}"
        print(f"✓ Non-participant correctly rejected with 403")

    def test_proximity_message_expiry_field(self, api_client):
        """Test POST /api/proximity/messages - Message has expires_at field with 24h expiry"""
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        join = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join.json()["room_id"]
        
        # Send message
        message_data = {
            "room_id": room_id,
            "content": "Test expiry message",
            "msg_type": "text"
        }
        response = api_client.post(
            f"{BASE_URL}/api/proximity/messages",
            headers={"Authorization": f"Bearer {token}"},
            json=message_data
        )
        assert response.status_code == 200
        
        msg = response.json()["message"]
        assert "expires_at" in msg
        
        # Verify expires_at is ~24 hours from now
        from datetime import datetime, timezone, timedelta
        created_at = datetime.fromisoformat(msg["created_at"].replace('Z', '+00:00'))
        expires_at = datetime.fromisoformat(msg["expires_at"].replace('Z', '+00:00'))
        expiry_delta = expires_at - created_at
        
        # Should be approximately 24 hours (allow 1 minute tolerance)
        expected_hours = 24
        actual_hours = expiry_delta.total_seconds() / 3600
        assert abs(actual_hours - expected_hours) < 0.02, f"Expected ~24h expiry, got {actual_hours}h"
        
        print(f"✓ Message expires in {actual_hours:.2f} hours (expected 24h)")

    def test_join_proximity_room_unauthenticated(self, api_client):
        """Test POST /api/proximity/join without authentication"""
        response = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        assert response.status_code == 401
        print("✓ Unauthenticated join request rejected")

    def test_get_proximity_room_not_found(self, api_client):
        """Test GET /api/proximity/room/{room_id} with non-existent room"""
        login = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = login.json()["token"]
        
        response = api_client.get(
            f"{BASE_URL}/api/proximity/room/prox_invalid_room_id",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404
        print("✓ Non-existent room returns 404")
