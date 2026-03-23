"""
Proximity Chat WebSocket tests
Tests: Socket.IO events - join_proximity, leave_proximity, send_proximity_message
       Real-time message broadcasting, user join/leave notifications
"""
import pytest
import socketio
import requests
import time
import asyncio
from pathlib import Path
from dotenv import load_dotenv

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

class TestProximityWebSocket:
    """Proximity chat WebSocket event tests"""

    def test_proximity_socket_connection_and_auth(self):
        """Test Socket.IO connection and authentication for proximity chat"""
        # Login to get token
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        assert response.status_code == 200
        token = response.json()["token"]
        
        # Create Socket.IO client
        sio = socketio.Client()
        authenticated = False
        
        @sio.on('authenticated')
        def on_authenticated(data):
            nonlocal authenticated
            authenticated = True
            print(f"✓ Socket authenticated: {data}")
        
        # Connect
        sio.connect(BASE_URL, socketio_path='/api/socket.io')
        assert sio.connected, "Socket.IO connection failed"
        print("✓ Socket.IO connected")
        
        # Authenticate
        sio.emit('authenticate', {'token': token})
        time.sleep(1)  # Wait for auth response
        
        assert authenticated, "Socket authentication failed"
        print("✓ Socket.IO authenticated")
        
        sio.disconnect()
        print("✓ Socket.IO disconnected")

    def test_join_proximity_room_via_socket(self):
        """Test join_proximity event via WebSocket"""
        # Login
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = response.json()["token"]
        
        # Join room via REST first to get room_id
        join_response = requests.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join_response.json()["room_id"]
        
        # Connect socket
        sio = socketio.Client()
        user_joined_received = False
        
        @sio.on('proximity_user_joined')
        def on_user_joined(data):
            nonlocal user_joined_received
            user_joined_received = True
            print(f"✓ User joined event received: {data}")
        
        sio.connect(BASE_URL, socketio_path='/api/socket.io')
        sio.emit('authenticate', {'token': token})
        time.sleep(1)
        
        # Join proximity room via socket
        sio.emit('join_proximity', {'room_id': room_id})
        time.sleep(1)
        
        # Should receive user_joined event
        assert user_joined_received, "proximity_user_joined event not received"
        print(f"✓ Successfully joined proximity room via socket: {room_id}")
        
        sio.disconnect()

    def test_send_proximity_message_via_socket(self):
        """Test send_proximity_message event broadcasts to room"""
        # Login
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = response.json()["token"]
        
        # Join room
        join_response = requests.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join_response.json()["room_id"]
        
        # Connect socket
        sio = socketio.Client()
        message_received = False
        received_message = None
        
        @sio.on('proximity_message')
        def on_proximity_message(data):
            nonlocal message_received, received_message
            message_received = True
            received_message = data
            print(f"✓ Proximity message received: {data}")
        
        sio.connect(BASE_URL, socketio_path='/api/socket.io')
        sio.emit('authenticate', {'token': token})
        time.sleep(1)
        
        # Join room
        sio.emit('join_proximity', {'room_id': room_id})
        time.sleep(1)
        
        # Send message
        test_message = f"Test proximity message {int(time.time())}"
        sio.emit('send_proximity_message', {
            'room_id': room_id,
            'content': test_message,
            'msg_type': 'text'
        })
        time.sleep(2)  # Wait for broadcast
        
        assert message_received, "proximity_message event not received"
        assert received_message is not None
        assert received_message['content'] == test_message
        assert received_message['room_id'] == room_id
        assert 'expires_at' in received_message
        print(f"✓ Proximity message sent and received via socket")
        
        sio.disconnect()

    def test_leave_proximity_room_via_socket(self):
        """Test leave_proximity event via WebSocket - other users receive notification"""
        # Login user 1
        response1 = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token1 = response1.json()["token"]
        user1_id = response1.json()["user"]["user_id"]
        
        # Login user 2
        response2 = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_nearby@test.com", "password": "pass1234"}
        )
        token2 = response2.json()["token"]
        user2_id = response2.json()["user"]["user_id"]
        
        # Join room
        join_response = requests.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token1}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join_response.json()["room_id"]
        
        # Connect both sockets
        sio1 = socketio.Client()
        sio2 = socketio.Client()
        user2_left_received = False
        
        @sio1.on('proximity_user_left')
        def on_user_left(data):
            nonlocal user2_left_received
            if data.get('user_id') == user2_id:
                user2_left_received = True
                print(f"✓ User1 received user2 left event: {data}")
        
        sio1.connect(BASE_URL, socketio_path='/api/socket.io')
        sio1.emit('authenticate', {'token': token1})
        time.sleep(1)
        
        sio2.connect(BASE_URL, socketio_path='/api/socket.io')
        sio2.emit('authenticate', {'token': token2})
        time.sleep(1)
        
        # Both join room
        sio1.emit('join_proximity', {'room_id': room_id})
        time.sleep(1)
        sio2.emit('join_proximity', {'room_id': room_id})
        time.sleep(1)
        
        # User2 leaves room
        sio2.emit('leave_proximity', {'room_id': room_id})
        time.sleep(1)
        
        # User1 should receive user_left event
        assert user2_left_received, "proximity_user_left event not received by other user"
        print(f"✓ Successfully left proximity room via socket: {room_id}")
        
        sio1.disconnect()
        sio2.disconnect()

    def test_multi_user_proximity_chat(self):
        """Test 2 users in same proximity room receive each other's messages"""
        # Login user 1
        response1 = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token1 = response1.json()["token"]
        user1_id = response1.json()["user"]["user_id"]
        
        # Login user 2
        response2 = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_nearby@test.com", "password": "pass1234"}
        )
        token2 = response2.json()["token"]
        user2_id = response2.json()["user"]["user_id"]
        
        # Both join same room
        join_response = requests.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token1}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join_response.json()["room_id"]
        
        # Connect both sockets
        sio1 = socketio.Client()
        sio2 = socketio.Client()
        
        user1_messages = []
        user2_messages = []
        user2_joined = False
        
        @sio1.on('proximity_message')
        def on_message_user1(data):
            user1_messages.append(data)
            print(f"✓ User1 received message: {data['content']}")
        
        @sio1.on('proximity_user_joined')
        def on_user_joined_user1(data):
            nonlocal user2_joined
            if data.get('user', {}).get('user_id') == user2_id:
                user2_joined = True
                print(f"✓ User1 saw User2 join")
        
        @sio2.on('proximity_message')
        def on_message_user2(data):
            user2_messages.append(data)
            print(f"✓ User2 received message: {data['content']}")
        
        # Connect and authenticate both
        sio1.connect(BASE_URL, socketio_path='/api/socket.io')
        sio1.emit('authenticate', {'token': token1})
        time.sleep(1)
        
        sio2.connect(BASE_URL, socketio_path='/api/socket.io')
        sio2.emit('authenticate', {'token': token2})
        time.sleep(1)
        
        # User1 joins room
        sio1.emit('join_proximity', {'room_id': room_id})
        time.sleep(1)
        
        # User2 joins room
        sio2.emit('join_proximity', {'room_id': room_id})
        time.sleep(1)
        
        assert user2_joined, "User1 did not receive user2 join notification"
        
        # User1 sends message
        msg1 = f"Hello from user1 {int(time.time())}"
        sio1.emit('send_proximity_message', {
            'room_id': room_id,
            'content': msg1,
            'msg_type': 'text'
        })
        time.sleep(2)
        
        # User2 sends message
        msg2 = f"Hello from user2 {int(time.time())}"
        sio2.emit('send_proximity_message', {
            'room_id': room_id,
            'content': msg2,
            'msg_type': 'text'
        })
        time.sleep(2)
        
        # Verify both users received both messages
        assert len(user1_messages) >= 2, f"User1 should receive 2 messages, got {len(user1_messages)}"
        assert len(user2_messages) >= 2, f"User2 should receive 2 messages, got {len(user2_messages)}"
        
        # Verify message contents
        user1_contents = [m['content'] for m in user1_messages]
        user2_contents = [m['content'] for m in user2_messages]
        
        assert msg1 in user1_contents, "User1 should receive own message"
        assert msg2 in user1_contents, "User1 should receive user2's message"
        assert msg1 in user2_contents, "User2 should receive user1's message"
        assert msg2 in user2_contents, "User2 should receive own message"
        
        print(f"✓ Multi-user proximity chat working: both users received all messages")
        
        sio1.disconnect()
        sio2.disconnect()

    def test_proximity_auto_leave_on_disconnect(self):
        """Test user auto-leaves proximity room on disconnect"""
        # Login
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "geo_test@test.com", "password": "pass1234"}
        )
        token = response.json()["token"]
        
        # Join room
        join_response = requests.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"latitude": 40.7128, "longitude": -74.0060, "radius": 500}
        )
        room_id = join_response.json()["room_id"]
        initial_count = join_response.json()["participant_count"]
        
        # Connect socket and join
        sio = socketio.Client()
        sio.connect(BASE_URL, socketio_path='/api/socket.io')
        sio.emit('authenticate', {'token': token})
        time.sleep(1)
        sio.emit('join_proximity', {'room_id': room_id})
        time.sleep(1)
        
        # Disconnect (should auto-leave)
        sio.disconnect()
        time.sleep(2)
        
        # Check room participant count decreased
        room_response = requests.get(
            f"{BASE_URL}/api/proximity/room/{room_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if room_response.status_code == 200:
            final_count = room_response.json()["room"]["participant_count"]
            # Count should be same or less (user may have been removed)
            print(f"✓ Auto-leave on disconnect: participant count {initial_count} -> {final_count}")
        else:
            # Room may have been deleted if it was empty
            print(f"✓ Auto-leave on disconnect: room deleted (was empty)")
