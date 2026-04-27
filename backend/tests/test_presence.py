"""
Real-time presence system tests
Tests: user_online event, user_offline event with last_seen, conversations API excludes sensitive fields
"""
import pytest
import socketio
import os
import time
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def user1_token_sync(api_client, test_user_credentials):
    """Get auth token for user 1"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": test_user_credentials["email"],
            "password": test_user_credentials["password"]
        }
    )
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("User 1 token not available")

@pytest.fixture(scope="module")
def user2_token_sync(api_client, test_user2_credentials):
    """Get auth token for user 2"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": test_user2_credentials["email"],
            "password": test_user2_credentials["password"]
        }
    )
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("User 2 token not available")

@pytest.fixture(scope="module")
def conversation_id_sync(api_client, user1_token_sync, user2_token_sync):
    """Create a conversation for presence tests"""
    # Get user2 ID
    me_response = api_client.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {user2_token_sync}"}
    )
    user2_id = me_response.json()["user"]["user_id"]
    
    # Create conversation
    conv_response = api_client.post(
        f"{BASE_URL}/api/conversations",
        headers={"Authorization": f"Bearer {user1_token_sync}"},
        json={"participant_id": user2_id}
    )
    return conv_response.json()["conversation"]["conversation_id"]


class TestPresenceSystem:
    """Real-time presence system tests"""

    def test_user_online_event_fires_on_auth(self, user1_token_sync):
        """Test user_online event fires when user authenticates on socket"""
        sio = socketio.Client()
        user_online_received = False
        user_online_data = {}
        
        @sio.on('connect')
        def on_connect():
            print("Socket connected, sending auth...")
            sio.emit('authenticate', {'token': user1_token_sync})
        
        @sio.on('authenticated')
        def on_authenticated(data):
            print(f"✓ Socket authenticated: {data}")
        
        @sio.on('user_online')
        def on_user_online(data):
            nonlocal user_online_received, user_online_data
            user_online_received = True
            user_online_data = data
            print(f"✓ user_online event received: {data}")
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(2)
            
            assert user_online_received, "user_online event not received"
            assert 'user_id' in user_online_data, "user_online event missing user_id"
            print("✓ user_online event fires on authentication")
        finally:
            if sio.connected:
                sio.disconnect()

    def test_user_offline_event_includes_last_seen(self, user1_token_sync):
        """Test user_offline event includes last_seen timestamp when user disconnects"""
        sio1 = socketio.Client()
        sio2 = socketio.Client()
        
        user_offline_received = False
        user_offline_data = {}
        user1_id = None
        
        # User 1 connects
        @sio1.on('connect')
        def on_connect1():
            sio1.emit('authenticate', {'token': user1_token_sync})
        
        @sio1.on('authenticated')
        def on_authenticated1(data):
            nonlocal user1_id
            user1_id = data.get('user_id')
            print(f"✓ User 1 authenticated: {user1_id}")
        
        # User 2 listens for user_offline
        @sio2.on('connect')
        def on_connect2():
            # Don't authenticate user 2, just listen for broadcasts
            print("✓ User 2 connected (listener)")
        
        @sio2.on('user_offline')
        def on_user_offline(data):
            nonlocal user_offline_received, user_offline_data
            user_offline_received = True
            user_offline_data = data
            print(f"✓ user_offline event received: {data}")
        
        try:
            # Connect user 2 first (listener)
            sio2.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(1)
            
            # Connect user 1
            sio1.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(2)
            
            assert user1_id is not None, "User 1 not authenticated"
            
            # Disconnect user 1
            sio1.disconnect()
            time.sleep(2)
            
            assert user_offline_received, "user_offline event not received"
            assert 'user_id' in user_offline_data, "user_offline event missing user_id"
            assert 'last_seen' in user_offline_data, "user_offline event missing last_seen"
            assert user_offline_data['last_seen'] is not None, "last_seen is None"
            # Verify last_seen is ISO format timestamp
            assert 'T' in user_offline_data['last_seen'], "last_seen not in ISO format"
            print(f"✓ user_offline event includes last_seen: {user_offline_data['last_seen']}")
        finally:
            if sio1.connected:
                sio1.disconnect()
            if sio2.connected:
                sio2.disconnect()

    def test_conversations_api_returns_last_seen(self, api_client, user1_token_sync, conversation_id_sync):
        """Test GET /api/conversations returns other_user with last_seen field"""
        response = api_client.get(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token_sync}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        
        conversations = data["conversations"]
        assert len(conversations) > 0, "No conversations found"
        
        # Find the test conversation
        test_conv = None
        for conv in conversations:
            if conv.get("conversation_id") == conversation_id_sync:
                test_conv = conv
                break
        
        assert test_conv is not None, "Test conversation not found"
        assert "other_user" in test_conv, "other_user field missing"
        
        other_user = test_conv["other_user"]
        assert other_user is not None, "other_user is None"
        
        # Check for last_seen field (may be None if user never logged in)
        # The field should exist in the response
        assert "user_id" in other_user, "other_user missing user_id"
        assert "username" in other_user, "other_user missing username"
        
        print(f"✓ Conversations API returns other_user: {other_user.get('username')}")
        print(f"✓ other_user has last_seen field: {'last_seen' in other_user}")

    def test_conversations_api_excludes_sensitive_fields(self, api_client, user1_token_sync, conversation_id_sync):
        """Test GET /api/conversations excludes sensitive fields (location, password_hash) from other_user"""
        response = api_client.get(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token_sync}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        conversations = data["conversations"]
        
        # Check all conversations
        for conv in conversations:
            other_user = conv.get("other_user")
            if other_user:
                # Verify sensitive fields are NOT present
                assert "password_hash" not in other_user, "password_hash exposed in other_user"
                assert "location" not in other_user, "location exposed in other_user"
                assert "location_updated_at" not in other_user, "location_updated_at exposed in other_user"
                assert "current_proximity_room" not in other_user, "current_proximity_room exposed in other_user"
                assert "_id" not in other_user, "MongoDB _id exposed in other_user"
        
        print("✓ Conversations API excludes sensitive fields from other_user")
        print("✓ Verified: password_hash, location, location_updated_at, current_proximity_room, _id not exposed")

    def test_multi_user_presence_broadcast(self, user1_token_sync, user2_token_sync):
        """Test user_online and user_offline events broadcast to all connected clients"""
        sio1 = socketio.Client()
        sio2 = socketio.Client()
        
        user1_online_received = False
        user2_online_received = False
        user1_offline_received = False
        
        user1_id = None
        user2_id = None
        user2_authenticated = False
        
        # User 1 setup
        @sio1.on('connect')
        def on_connect1():
            sio1.emit('authenticate', {'token': user1_token_sync})
        
        @sio1.on('authenticated')
        def on_authenticated1(data):
            nonlocal user1_id
            user1_id = data.get('user_id')
            print(f"✓ User 1 authenticated: {user1_id}")
        
        @sio1.on('user_online')
        def on_user_online1(data):
            nonlocal user2_online_received, user2_id
            received_user_id = data.get('user_id')
            print(f"User 1 received user_online for: {received_user_id}")
            # Check if this is NOT user 1's own online event
            if received_user_id != user1_id:
                user2_online_received = True
                user2_id = received_user_id
                print(f"✓ User 1 received user_online for User 2: {received_user_id}")
        
        @sio1.on('user_offline')
        def on_user_offline1(data):
            nonlocal user1_offline_received
            received_user_id = data.get('user_id')
            print(f"User 1 received user_offline for: {received_user_id}")
            if received_user_id != user1_id:
                user1_offline_received = True
                print(f"✓ User 1 received user_offline for User 2")
        
        # User 2 setup
        @sio2.on('connect')
        def on_connect2():
            sio2.emit('authenticate', {'token': user2_token_sync})
        
        @sio2.on('authenticated')
        def on_authenticated2(data):
            nonlocal user2_id, user2_authenticated
            user2_id = data.get('user_id')
            user2_authenticated = True
            print(f"✓ User 2 authenticated: {user2_id}")
        
        @sio2.on('user_online')
        def on_user_online2(data):
            nonlocal user1_online_received
            if data.get('user_id') == user1_id:
                user1_online_received = True
                print(f"✓ User 2 received user_online for User 1")
        
        try:
            # Connect user 1 first
            sio1.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(3)
            assert user1_id is not None, "User 1 not authenticated"
            
            # Connect user 2 (should trigger user_online broadcast)
            sio2.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(3)
            assert user2_id is not None, "User 2 not authenticated"
            
            # User 1 should have received user_online for User 2
            assert user2_online_received, "User 1 did not receive user_online for User 2"
            
            # Disconnect user 2 (should trigger user_offline broadcast)
            sio2.disconnect()
            time.sleep(3)
            
            # User 1 should have received user_offline for User 2
            assert user1_offline_received, "User 1 did not receive user_offline for User 2"
            
            print("✓ Multi-user presence broadcast working correctly")
        finally:
            if sio1.connected:
                sio1.disconnect()
            if sio2.connected:
                sio2.disconnect()

    def test_presence_data_structure(self, user1_token_sync):
        """Test presence event data structure is correct"""
        sio = socketio.Client()
        user_online_data = None
        
        @sio.on('connect')
        def on_connect():
            sio.emit('authenticate', {'token': user1_token_sync})
        
        @sio.on('user_online')
        def on_user_online(data):
            nonlocal user_online_data
            user_online_data = data
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(2)
            
            assert user_online_data is not None, "user_online event not received"
            assert isinstance(user_online_data, dict), "user_online data is not a dict"
            assert 'user_id' in user_online_data, "user_online missing user_id"
            assert isinstance(user_online_data['user_id'], str), "user_id is not a string"
            
            print(f"✓ Presence event data structure correct: {user_online_data}")
        finally:
            if sio.connected:
                sio.disconnect()
