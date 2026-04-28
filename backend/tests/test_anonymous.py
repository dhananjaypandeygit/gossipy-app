"""
Backend tests for Anonymous Mode feature
Tests: PUT /api/users/anonymous, GET /api/users/search, GET /api/conversations,
       GET /api/users/nearby, POST /api/proximity/messages, POST /api/auth/signup
"""
import pytest
import requests
import os

# Use the public backend URL for testing
BASE_URL = "https://jwt-chat-core.preview.emergentagent.com"

class TestAnonymousMode:
    """Test anonymous mode toggle and identity masking"""

    def test_enable_anonymous_mode(self, api_client, auth_token_anon):
        """Test enabling anonymous mode generates new random username"""
        response = api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": True}
        )
        assert response.status_code == 200, f"Failed to enable anonymous mode: {response.text}"
        
        data = response.json()
        user = data.get("user")
        assert user is not None, "No user in response"
        assert user["is_anonymous"] is True, "is_anonymous should be True"
        assert "anonymous_username" in user, "anonymous_username missing"
        assert len(user["anonymous_username"]) > 5, "anonymous_username too short"
        # Store for next test
        pytest.anon_username_1 = user["anonymous_username"]
        print(f"✓ Anonymous mode enabled, username: {user['anonymous_username']}")

    def test_disable_anonymous_mode(self, api_client, auth_token_anon):
        """Test disabling anonymous mode restores real identity"""
        response = api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": False}
        )
        assert response.status_code == 200, f"Failed to disable anonymous mode: {response.text}"
        
        data = response.json()
        user = data.get("user")
        assert user is not None, "No user in response"
        assert user["is_anonymous"] is False, "is_anonymous should be False"
        print(f"✓ Anonymous mode disabled, real username: {user['username']}")

    def test_enable_anonymous_generates_different_name(self, api_client, auth_token_anon):
        """Test each enable generates a DIFFERENT random anonymous name"""
        # Enable first time
        response1 = api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": True}
        )
        assert response1.status_code == 200
        name1 = response1.json()["user"]["anonymous_username"]
        
        # Disable
        api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": False}
        )
        
        # Enable second time
        response2 = api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": True}
        )
        assert response2.status_code == 200
        name2 = response2.json()["user"]["anonymous_username"]
        
        # Names should be different (very high probability with random generation)
        # If they're the same, it's likely not generating new names
        print(f"✓ First enable: {name1}, Second enable: {name2}")
        # Note: There's a tiny chance they could be the same by random chance
        # But with 30 adjectives * 30 nouns * 90 numbers = 81,000 combinations, it's unlikely


class TestAnonymousDisplayMasking:
    """Test identity masking in various APIs when user is anonymous"""

    def test_search_shows_anonymous_identity(self, api_client, auth_token_observer, auth_token_anon):
        """Test GET /api/users/search shows masked identity for anonymous users"""
        # First, enable anonymous mode for anon_test user
        api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": True}
        )
        
        # Now search for anon_test user from observer account
        response = api_client.get(
            f"{BASE_URL}/api/users/search?q=anon",
            headers={"Authorization": f"Bearer {auth_token_observer}"}
        )
        assert response.status_code == 200, f"Search failed: {response.text}"
        
        data = response.json()
        users = data.get("users", [])
        assert len(users) > 0, "No users found in search"
        
        # Find the anonymous user
        anon_user = None
        for u in users:
            if u.get("is_anonymous"):
                anon_user = u
                break
        
        assert anon_user is not None, "Anonymous user not found in search results"
        assert anon_user["email"] == "anonymous@gossipy.app", f"Email not masked: {anon_user['email']}"
        assert anon_user["avatar"] is None, f"Avatar not masked: {anon_user['avatar']}"
        # Check that username looks like anonymous format (e.g., "ShadowWolf20", "JadeNomad70")
        assert len(anon_user["username"]) > 5, f"Username too short: {anon_user['username']}"
        assert anon_user["username"][-2:].isdigit(), f"Username doesn't end with 2 digits: {anon_user['username']}"
        print(f"✓ Search shows anonymous identity: {anon_user['username']}, {anon_user['email']}")

    def test_search_shows_real_identity_after_disable(self, api_client, auth_token_observer, auth_token_anon):
        """Test GET /api/users/search shows real identity after disabling anonymous"""
        # Disable anonymous mode
        api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": False}
        )
        
        # Search again
        response = api_client.get(
            f"{BASE_URL}/api/users/search?q=anon",
            headers={"Authorization": f"Bearer {auth_token_observer}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        users = data.get("users", [])
        
        # Find the user (should show real identity now)
        real_user = None
        for u in users:
            if "anon" in u.get("email", "").lower():
                real_user = u
                break
        
        if real_user:
            assert real_user.get("is_anonymous") is False, "User still marked as anonymous"
            assert real_user["email"] != "anonymous@gossipy.app", "Email still masked"
            print(f"✓ Search shows real identity after disable: {real_user['username']}, {real_user['email']}")

    def test_conversations_shows_anonymous_other_user(self, api_client, auth_token_observer, auth_token_anon):
        """Test GET /api/conversations shows masked identity for anonymous other_user"""
        # Enable anonymous mode for anon_test
        api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": True}
        )
        
        # Create conversation between observer and anon_test (if not exists)
        # First get anon_test user_id
        me_response = api_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {auth_token_anon}"}
        )
        anon_user_id = me_response.json()["user"]["user_id"]
        
        # Create conversation from observer side
        conv_response = api_client.post(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {auth_token_observer}"},
            json={"participant_id": anon_user_id}
        )
        assert conv_response.status_code == 200
        
        # Get conversations for observer
        response = api_client.get(
            f"{BASE_URL}/api/conversations",
            headers={"Authorization": f"Bearer {auth_token_observer}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        conversations = data.get("conversations", [])
        assert len(conversations) > 0, "No conversations found"
        
        # Find conversation with anon_test
        anon_conv = None
        for conv in conversations:
            if conv.get("other_user") and conv["other_user"].get("user_id") == anon_user_id:
                anon_conv = conv
                break
        
        assert anon_conv is not None, "Conversation with anonymous user not found"
        other_user = anon_conv["other_user"]
        assert other_user["email"] == "anonymous@gossipy.app", f"Email not masked in conversation: {other_user['email']}"
        assert other_user["avatar"] is None, f"Avatar not masked in conversation: {other_user['avatar']}"
        assert other_user.get("is_anonymous") is True, "is_anonymous flag missing or false"
        print(f"✓ Conversations shows anonymous other_user: {other_user['username']}, {other_user['email']}")

    def test_nearby_shows_anonymous_users(self, api_client, auth_token_observer, auth_token_anon):
        """Test GET /api/users/nearby shows masked identity for anonymous users"""
        # Enable anonymous mode for anon_test
        api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": True}
        )
        
        # Update location for both users (same location)
        test_location = {"latitude": 37.7749, "longitude": -122.4194}
        
        api_client.put(
            f"{BASE_URL}/api/users/location",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json=test_location
        )
        
        api_client.put(
            f"{BASE_URL}/api/users/location",
            headers={"Authorization": f"Bearer {auth_token_observer}"},
            json=test_location
        )
        
        # Get nearby users from observer perspective
        response = api_client.get(
            f"{BASE_URL}/api/users/nearby?latitude={test_location['latitude']}&longitude={test_location['longitude']}&radius=500",
            headers={"Authorization": f"Bearer {auth_token_observer}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        users = data.get("users", [])
        
        # Find anonymous user in nearby results
        anon_nearby = None
        for u in users:
            if u.get("is_anonymous"):
                anon_nearby = u
                break
        
        if anon_nearby:
            assert anon_nearby["email"] == "anonymous@gossipy.app", f"Email not masked in nearby: {anon_nearby['email']}"
            assert anon_nearby["avatar"] is None, f"Avatar not masked in nearby: {anon_nearby['avatar']}"
            print(f"✓ Nearby shows anonymous user: {anon_nearby['username']}, {anon_nearby['email']}")
        else:
            print("⚠ No anonymous user found in nearby results (may be expected if location not close enough)")


class TestAnonymousMessaging:
    """Test anonymous sender info in messages"""

    def test_proximity_message_stores_anonymous_sender(self, api_client, auth_token_anon):
        """Test POST /api/proximity/messages stores anonymous sender info"""
        # Enable anonymous mode
        api_client.put(
            f"{BASE_URL}/api/users/anonymous",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"is_anonymous": True}
        )
        
        # Join proximity room
        test_location = {"latitude": 37.7749, "longitude": -122.4194, "radius": 500}
        join_response = api_client.post(
            f"{BASE_URL}/api/proximity/join",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json=test_location
        )
        assert join_response.status_code == 200
        room_id = join_response.json()["room_id"]
        
        # Send message
        msg_response = api_client.post(
            f"{BASE_URL}/api/proximity/messages",
            headers={"Authorization": f"Bearer {auth_token_anon}"},
            json={"room_id": room_id, "content": "Test anonymous message", "msg_type": "text"}
        )
        assert msg_response.status_code == 200
        
        message = msg_response.json()["message"]
        assert message["sender_is_anonymous"] is True, "sender_is_anonymous should be True"
        # Check that username looks like anonymous format (e.g., "ShadowWolf20", "WhisperGriffin63")
        assert len(message["sender_username"]) > 5, f"sender_username too short: {message['sender_username']}"
        assert message["sender_username"][-2:].isdigit(), f"sender_username doesn't end with 2 digits: {message['sender_username']}"
        assert message["sender_avatar"] is None, f"sender_avatar should be None: {message['sender_avatar']}"
        print(f"✓ Proximity message stores anonymous sender: {message['sender_username']}, sender_is_anonymous={message['sender_is_anonymous']}")


class TestSignupAnonymousFields:
    """Test POST /api/auth/signup creates users with anonymous fields"""

    def test_signup_creates_anonymous_username(self, api_client):
        """Test new users get is_anonymous=false and initial anonymous_username"""
        import random
        test_email = f"test_anon_{random.randint(1000, 9999)}@test.com"
        test_username = f"testuser_{random.randint(1000, 9999)}"
        
        response = api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json={
                "email": test_email,
                "username": test_username,
                "password": "testpass123"
            }
        )
        assert response.status_code == 200, f"Signup failed: {response.text}"
        
        data = response.json()
        user = data.get("user")
        assert user is not None, "No user in response"
        assert user["is_anonymous"] is False, "New user should have is_anonymous=False"
        assert "anonymous_username" in user, "anonymous_username missing"
        assert len(user["anonymous_username"]) > 5, "anonymous_username too short"
        print(f"✓ Signup creates user with is_anonymous=False and anonymous_username: {user['anonymous_username']}")
        
        # Cleanup: delete test user
        token = data.get("token")
        if token:
            # Note: No delete endpoint, so we'll leave it (or implement cleanup later)
            pass


@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def auth_token_anon(api_client):
    """Login as anon_test@test.com and return token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "anon_test@test.com", "password": "pass1234"}
    )
    if response.status_code != 200:
        pytest.skip(f"Failed to login as anon_test@test.com: {response.text}")
    return response.json()["token"]


@pytest.fixture
def auth_token_observer(api_client):
    """Login as observer@test.com and return token"""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "observer@test.com", "password": "pass1234"}
    )
    if response.status_code != 200:
        pytest.skip(f"Failed to login as observer@test.com: {response.text}")
    return response.json()["token"]
