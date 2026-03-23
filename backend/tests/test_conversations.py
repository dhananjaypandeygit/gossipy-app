"""
Conversation and message endpoint tests
Tests: list conversations, create conversation, get messages, send message, mark as read
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def user1_token(api_client, test_user_credentials):
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
def user2_token_and_id(api_client, test_user2_credentials):
    """Get auth token and user_id for user 2"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": test_user2_credentials["email"],
            "password": test_user2_credentials["password"]
        }
    )
    if response.status_code == 200:
        data = response.json()
        return data["token"], data["user"]["user_id"]
    pytest.skip("User 2 token not available")

class TestConversations:
    """Conversation management tests"""

    def test_get_conversations_empty(self, api_client, user1_token):
        """Test getting conversations when none exist"""
        response = api_client.get(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert isinstance(data["conversations"], list)
        print("✓ GET /api/conversations successful")

    def test_create_conversation(self, api_client, user1_token, user2_token_and_id):
        """Test creating a conversation between two users"""
        _, user2_id = user2_token_and_id
        
        response = api_client.post(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={"participant_id": user2_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert "conversation" in data
        assert "conversation_id" in data["conversation"]
        assert user2_id in data["conversation"]["participants"]
        
        # Verify persistence - GET conversations
        get_response = api_client.get(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        assert get_response.status_code == 200
        conversations = get_response.json()["conversations"]
        assert len(conversations) > 0
        found = any(c["conversation_id"] == data["conversation"]["conversation_id"] for c in conversations)
        assert found, "Created conversation not found in list"
        print(f"✓ Conversation created: {data['conversation']['conversation_id']}")

    def test_create_conversation_duplicate(self, api_client, user1_token, user2_token_and_id):
        """Test creating duplicate conversation returns existing one"""
        _, user2_id = user2_token_and_id
        
        # Create first conversation
        response1 = api_client.post(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={"participant_id": user2_id}
        )
        conv_id_1 = response1.json()["conversation"]["conversation_id"]
        
        # Try to create again
        response2 = api_client.post(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={"participant_id": user2_id}
        )
        assert response2.status_code == 200
        conv_id_2 = response2.json()["conversation"]["conversation_id"]
        assert conv_id_1 == conv_id_2, "Should return existing conversation"
        print("✓ Duplicate conversation returns existing")

    def test_create_conversation_invalid_user(self, api_client, user1_token):
        """Test creating conversation with non-existent user"""
        response = api_client.post(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={"participant_id": "invalid_user_id_12345"}
        )
        assert response.status_code == 404
        print("✓ Invalid participant rejected")

    def test_get_conversation_messages_empty(self, api_client, user1_token, user2_token_and_id):
        """Test getting messages from a conversation with no messages"""
        _, user2_id = user2_token_and_id
        
        # Get or create conversation
        conv_response = api_client.post(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={"participant_id": user2_id}
        )
        conv_id = conv_response.json()["conversation"]["conversation_id"]
        
        # Get messages
        response = api_client.get(
            f"{BASE_URL}/api/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert isinstance(data["messages"], list)
        print(f"✓ GET messages successful for conversation {conv_id}")

    def test_get_conversation_messages_unauthorized(self, api_client, user1_token):
        """Test getting messages from conversation user is not part of"""
        response = api_client.get(
            f"{BASE_URL}/api/conversations/invalid_conv_id/messages",
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        assert response.status_code == 404
        print("✓ Unauthorized conversation access rejected")


class TestMessages:
    """Message sending and management tests"""

    @pytest.fixture(scope="class")
    def conversation_id(self, api_client, user1_token, user2_token_and_id):
        """Create a conversation for message tests"""
        _, user2_id = user2_token_and_id
        response = api_client.post(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={"participant_id": user2_id}
        )
        return response.json()["conversation"]["conversation_id"]

    def test_send_text_message(self, api_client, user1_token, conversation_id):
        """Test sending a text message"""
        response = api_client.post(
            f"{BASE_URL}/api/messages",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={
                "conversation_id": conversation_id,
                "content": "Hello, this is a test message!",
                "msg_type": "text"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"]["content"] == "Hello, this is a test message!"
        assert data["message"]["conversation_id"] == conversation_id
        assert "message_id" in data["message"]
        
        # Verify persistence - GET messages
        get_response = api_client.get(
            f"{BASE_URL}/api/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {user1_token}"}
        )
        assert get_response.status_code == 200
        messages = get_response.json()["messages"]
        assert len(messages) > 0
        found = any(m["message_id"] == data["message"]["message_id"] for m in messages)
        assert found, "Sent message not found in conversation"
        print(f"✓ Text message sent: {data['message']['message_id']}")

    def test_send_image_message(self, api_client, user1_token, conversation_id):
        """Test sending an image message"""
        test_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        
        response = api_client.post(
            f"{BASE_URL}/api/messages",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={
                "conversation_id": conversation_id,
                "content": None,
                "image": test_image,
                "msg_type": "image"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"]["image"] == test_image
        assert data["message"]["msg_type"] == "image"
        print(f"✓ Image message sent")

    def test_send_message_invalid_conversation(self, api_client, user1_token):
        """Test sending message to non-existent conversation"""
        response = api_client.post(
            f"{BASE_URL}/api/messages",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={
                "conversation_id": "invalid_conv_id_12345",
                "content": "Test message",
                "msg_type": "text"
            }
        )
        assert response.status_code == 404
        print("✓ Invalid conversation rejected")

    def test_mark_messages_as_read(self, api_client, user1_token, user2_token_and_id, conversation_id):
        """Test marking messages as read"""
        user2_token, _ = user2_token_and_id
        
        # User 1 sends a message
        send_response = api_client.post(
            f"{BASE_URL}/api/messages",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={
                "conversation_id": conversation_id,
                "content": "Message to be marked as read",
                "msg_type": "text"
            }
        )
        assert send_response.status_code == 200
        
        # User 2 marks messages as read
        read_response = api_client.post(
            f"{BASE_URL}/api/messages/read",
            headers={"Authorization": f"Bearer {user2_token}"},
            json={"conversation_id": conversation_id}
        )
        assert read_response.status_code == 200
        data = read_response.json()
        assert data["success"] == True
        print("✓ Messages marked as read")

    def test_mark_messages_read_missing_conversation_id(self, api_client, user1_token):
        """Test marking messages as read without conversation_id"""
        response = api_client.post(
            f"{BASE_URL}/api/messages/read",
            headers={"Authorization": f"Bearer {user1_token}"},
            json={}
        )
        assert response.status_code == 400
        print("✓ Missing conversation_id rejected")
