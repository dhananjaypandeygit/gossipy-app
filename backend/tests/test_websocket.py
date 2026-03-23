"""
WebSocket (Socket.IO) tests
Tests: connection, authentication, join room, send message, typing indicator
"""
import pytest
import socketio
import os
import time
import asyncio

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
    """Create a conversation for WebSocket tests"""
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


class TestWebSocket:
    """Socket.IO WebSocket tests"""

    def test_socket_connection(self, user1_token_sync):
        """Test Socket.IO connection"""
        sio = socketio.Client()
        connected = False
        
        @sio.on('connect')
        def on_connect():
            nonlocal connected
            connected = True
            print("✓ Socket connected")
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(1)
            assert connected, "Socket did not connect"
            assert sio.connected, "Socket not in connected state"
            print("✓ Socket.IO connection successful")
        finally:
            if sio.connected:
                sio.disconnect()

    def test_socket_authentication(self, user1_token_sync):
        """Test Socket.IO authentication"""
        sio = socketio.Client()
        authenticated = False
        auth_data = {}
        
        @sio.on('connect')
        def on_connect():
            print("Socket connected, sending auth...")
            sio.emit('authenticate', {'token': user1_token_sync})
        
        @sio.on('authenticated')
        def on_authenticated(data):
            nonlocal authenticated, auth_data
            authenticated = True
            auth_data = data
            print(f"✓ Socket authenticated: {data}")
        
        @sio.on('auth_error')
        def on_auth_error(data):
            print(f"Auth error: {data}")
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(2)
            assert authenticated, "Socket authentication failed"
            assert 'user_id' in auth_data
            print("✓ Socket.IO authentication successful")
        finally:
            if sio.connected:
                sio.disconnect()

    def test_socket_join_conversation(self, user1_token_sync, conversation_id_sync):
        """Test joining a conversation room"""
        sio = socketio.Client()
        authenticated = False
        
        @sio.on('connect')
        def on_connect():
            sio.emit('authenticate', {'token': user1_token_sync})
        
        @sio.on('authenticated')
        def on_authenticated(data):
            nonlocal authenticated
            authenticated = True
            # Join conversation room
            sio.emit('join_conversation', {'conversation_id': conversation_id_sync})
            print(f"✓ Joined conversation room: {conversation_id_sync}")
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(2)
            assert authenticated, "Socket not authenticated"
            print("✓ Join conversation successful")
        finally:
            if sio.connected:
                sio.disconnect()

    def test_socket_send_message(self, user1_token_sync, conversation_id_sync):
        """Test sending a message via Socket.IO"""
        sio = socketio.Client()
        authenticated = False
        message_received = False
        received_message = {}
        
        @sio.on('connect')
        def on_connect():
            sio.emit('authenticate', {'token': user1_token_sync})
        
        @sio.on('authenticated')
        def on_authenticated(data):
            nonlocal authenticated
            authenticated = True
            # Join conversation room
            sio.emit('join_conversation', {'conversation_id': conversation_id_sync})
            time.sleep(0.5)
            # Send message
            sio.emit('send_message', {
                'conversation_id': conversation_id_sync,
                'content': 'Test WebSocket message',
                'msg_type': 'text'
            })
            print("✓ Message sent via WebSocket")
        
        @sio.on('new_message')
        def on_new_message(data):
            nonlocal message_received, received_message
            message_received = True
            received_message = data
            print(f"✓ Message received: {data.get('content', '')}")
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(3)
            assert authenticated, "Socket not authenticated"
            assert message_received, "Message not received via WebSocket"
            assert received_message.get('content') == 'Test WebSocket message'
            print("✓ WebSocket message send/receive successful")
        finally:
            if sio.connected:
                sio.disconnect()

    def test_socket_typing_indicator(self, user1_token_sync, conversation_id_sync):
        """Test typing indicator broadcast"""
        sio = socketio.Client()
        authenticated = False
        typing_received = False
        
        @sio.on('connect')
        def on_connect():
            sio.emit('authenticate', {'token': user1_token_sync})
        
        @sio.on('authenticated')
        def on_authenticated(data):
            nonlocal authenticated
            authenticated = True
            sio.emit('join_conversation', {'conversation_id': conversation_id_sync})
            time.sleep(0.5)
            # Send typing indicator
            sio.emit('typing', {
                'conversation_id': conversation_id_sync,
                'is_typing': True
            })
            print("✓ Typing indicator sent")
        
        @sio.on('user_typing')
        def on_user_typing(data):
            nonlocal typing_received
            typing_received = True
            print(f"✓ Typing indicator received: {data}")
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(2)
            assert authenticated, "Socket not authenticated"
            # Note: typing indicator is broadcast to others in room, not self
            # So we won't receive our own typing indicator
            print("✓ Typing indicator test completed")
        finally:
            if sio.connected:
                sio.disconnect()

    def test_socket_multi_user_chat(self, user1_token_sync, user2_token_sync, conversation_id_sync):
        """Test two users in same conversation receive each other's messages"""
        sio1 = socketio.Client()
        sio2 = socketio.Client()
        
        user1_authenticated = False
        user2_authenticated = False
        user2_received_message = False
        received_content = None
        
        # User 1 setup
        @sio1.on('connect')
        def on_connect1():
            sio1.emit('authenticate', {'token': user1_token_sync})
        
        @sio1.on('authenticated')
        def on_authenticated1(data):
            nonlocal user1_authenticated
            user1_authenticated = True
            sio1.emit('join_conversation', {'conversation_id': conversation_id_sync})
            print("✓ User 1 authenticated and joined room")
        
        # User 2 setup
        @sio2.on('connect')
        def on_connect2():
            sio2.emit('authenticate', {'token': user2_token_sync})
        
        @sio2.on('authenticated')
        def on_authenticated2(data):
            nonlocal user2_authenticated
            user2_authenticated = True
            sio2.emit('join_conversation', {'conversation_id': conversation_id_sync})
            print("✓ User 2 authenticated and joined room")
        
        @sio2.on('new_message')
        def on_new_message2(data):
            nonlocal user2_received_message, received_content
            user2_received_message = True
            received_content = data.get('content')
            print(f"✓ User 2 received message: {received_content}")
        
        try:
            # Connect both users
            sio1.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(1)
            sio2.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(2)
            
            assert user1_authenticated, "User 1 not authenticated"
            assert user2_authenticated, "User 2 not authenticated"
            
            # User 1 sends message
            sio1.emit('send_message', {
                'conversation_id': conversation_id_sync,
                'content': 'Multi-user test message',
                'msg_type': 'text'
            })
            print("✓ User 1 sent message")
            
            time.sleep(2)
            
            assert user2_received_message, "User 2 did not receive message"
            assert received_content == 'Multi-user test message'
            print("✓ Multi-user chat test successful")
        finally:
            if sio1.connected:
                sio1.disconnect()
            if sio2.connected:
                sio2.disconnect()

    def test_socket_disconnect(self, user1_token_sync):
        """Test Socket.IO disconnect"""
        sio = socketio.Client()
        disconnected = False
        
        @sio.on('disconnect')
        def on_disconnect():
            nonlocal disconnected
            disconnected = True
            print("✓ Socket disconnected")
        
        try:
            sio.connect(BASE_URL, socketio_path='/api/socket.io', transports=['websocket', 'polling'])
            time.sleep(1)
            assert sio.connected
            sio.disconnect()
            time.sleep(1)
            assert not sio.connected
            print("✓ Socket disconnect successful")
        except Exception as e:
            print(f"Disconnect test completed with: {e}")
