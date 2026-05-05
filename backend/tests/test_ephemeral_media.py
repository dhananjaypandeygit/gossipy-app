"""
Ephemeral Media Feature Tests
Tests for view-once/view-twice media with JWT-based signed URLs
"""
import pytest
import requests
import os
import time
import base64

# Use backend URL from review request
BASE_URL = "https://jwt-chat-core.preview.emergentagent.com"

# Sample base64 image (1x1 red pixel PNG)
SAMPLE_IMAGE_BASE64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

# Sample base64 video (minimal MP4 header)
SAMPLE_VIDEO_BASE64 = "data:video/mp4;base64,AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAAAu1tZGF0"

# Sample base64 audio (minimal MP3 header)
SAMPLE_AUDIO_BASE64 = "data:audio/mpeg;base64,//uQxAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAADhAC"


class TestEphemeralMediaUpload:
    """Test media upload endpoint with different view limits"""

    def test_upload_view_once_image(self, api_client, test_user_credentials):
        """POST /api/media/upload - Upload image with view_limit=1"""
        # Login first
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        
        # Upload view-once image
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        data = upload_res.json()
        assert "media_id" in data
        assert data["media_category"] == "image"
        assert data["view_limit"] == 1
        assert data["message"] is None  # No conversation_id provided
        print(f"✓ View-once image uploaded: {data['media_id']}")

    def test_upload_view_twice_video(self, api_client, test_user_credentials):
        """POST /api/media/upload - Upload video with view_limit=2"""
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "content": SAMPLE_VIDEO_BASE64,
                "mime_type": "video/mp4",
                "view_limit": 2
            }
        )
        assert upload_res.status_code == 200
        data = upload_res.json()
        assert "media_id" in data
        assert data["media_category"] == "video"
        assert data["view_limit"] == 2
        print(f"✓ View-twice video uploaded: {data['media_id']}")

    def test_upload_with_conversation_auto_sends_message(self, api_client, test_user_credentials):
        """POST /api/media/upload - With conversation_id auto-sends ephemeral message"""
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        
        # Use existing conversation
        conversation_id = "conv_8c4ea343ab14"
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/jpeg",
                "view_limit": 1,
                "conversation_id": conversation_id
            }
        )
        assert upload_res.status_code == 200
        data = upload_res.json()
        assert "media_id" in data
        assert "message" in data
        assert data["message"] is not None
        
        # Verify message structure
        msg = data["message"]
        assert msg["conversation_id"] == conversation_id
        assert msg["msg_type"] == "ephemeral_image"
        assert msg["media_id"] == data["media_id"]
        assert msg["media_view_limit"] == 1
        assert "🔥" in msg["content"]  # View-once emoji
        print(f"✓ Ephemeral message auto-sent: {msg['message_id']}")

    def test_upload_invalid_mime_type_returns_400(self, api_client, test_user_credentials):
        """POST /api/media/upload - Invalid mime_type returns 400"""
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "content": "data:application/pdf;base64,JVBERi0xLjQK",
                "mime_type": "application/pdf",  # Not allowed
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 400
        assert "Unsupported mime type" in upload_res.json()["detail"]
        print("✓ Invalid mime_type rejected with 400")


class TestMediaAccessToken:
    """Test media access token generation"""

    def test_get_token_for_viewable_media(self, api_client, test_user_credentials, test_user2_credentials):
        """GET /api/media/{id}/token - Returns signed access token with 60s expiry"""
        # User 1 uploads media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 requests access token
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res.status_code == 200
        data = token_res.json()
        assert "access_token" in data
        assert data["media_id"] == media_id
        assert data["expires_in"] == 60
        assert data["views_remaining"] == 1
        print(f"✓ Access token generated for {media_id}")

    def test_get_token_after_view_limit_returns_410(self, api_client, test_user_credentials, test_user2_credentials):
        """GET /api/media/{id}/token - Returns 410 after view limit reached"""
        # User 1 uploads view-once media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 views the media (exhausts view limit)
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        # Get token and view
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res.status_code == 200
        access_token = token_res.json()["access_token"]
        
        view_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/view?token={access_token}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res.status_code == 200
        
        # Try to get token again - should return 410
        token_res2 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res2.status_code == 410
        detail = token_res2.json()["detail"].lower()
        assert "expired" in detail or "already viewed" in detail
        print("✓ Token request returns 410 after view limit reached")


class TestMediaViewing:
    """Test media viewing with signed tokens"""

    def test_view_media_with_valid_token(self, api_client, test_user_credentials, test_user2_credentials):
        """GET /api/media/{id}/view?token=xxx - Returns media content and increments view count"""
        # User 1 uploads media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 gets token and views
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res.status_code == 200
        access_token = token_res.json()["access_token"]
        
        view_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/view?token={access_token}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res.status_code == 200
        data = view_res.json()
        assert data["media_id"] == media_id
        assert "content" in data
        assert data["mime_type"] == "image/png"
        assert data["views_used"] == 1
        assert data["is_final_view"] is True
        print(f"✓ Media viewed successfully: {media_id}")

    def test_view_with_expired_token_returns_401(self, api_client, test_user_credentials, test_user2_credentials):
        """GET /api/media/{id}/view?token=xxx - Expired token returns 401"""
        # User 1 uploads media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 gets token
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res.status_code == 200
        access_token = token_res.json()["access_token"]
        
        # Wait for token to expire (61 seconds)
        print("⏳ Waiting 61 seconds for token to expire...")
        time.sleep(61)
        
        # Try to view with expired token
        view_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/view?token={access_token}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res.status_code == 401
        assert "expired" in view_res.json()["detail"].lower()
        print("✓ Expired token rejected with 401")

    def test_view_once_second_view_returns_410(self, api_client, test_user_credentials, test_user2_credentials):
        """GET /api/media/{id}/view - View-once media: second view attempt returns 410"""
        # User 1 uploads view-once media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 views once
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        # First view
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res.status_code == 200
        access_token = token_res.json()["access_token"]
        
        view_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/view?token={access_token}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res.status_code == 200
        
        # Try to get token for second view - should return 410
        token_res2 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res2.status_code == 410
        print("✓ View-once media blocks second view with 410")

    def test_view_twice_allows_2_views_blocks_3rd(self, api_client, test_user_credentials, test_user2_credentials):
        """GET /api/media/{id}/view - View-twice media: allows 2 views, blocks 3rd"""
        # User 1 uploads view-twice media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 2
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 views twice
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        # First view
        token_res1 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res1.status_code == 200
        assert token_res1.json()["views_remaining"] == 2
        
        view_res1 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/view?token={token_res1.json()['access_token']}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res1.status_code == 200
        assert view_res1.json()["views_used"] == 1
        assert view_res1.json()["is_final_view"] is False
        print("✓ First view successful")
        
        # Second view
        token_res2 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res2.status_code == 200
        assert token_res2.json()["views_remaining"] == 1
        
        view_res2 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/view?token={token_res2.json()['access_token']}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res2.status_code == 200
        assert view_res2.json()["views_used"] == 2
        assert view_res2.json()["is_final_view"] is True
        print("✓ Second view successful")
        
        # Third view attempt - should return 410
        token_res3 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res3.status_code == 410
        print("✓ View-twice media blocks 3rd view with 410")


class TestMediaStatus:
    """Test media status endpoint"""

    def test_status_returns_correct_viewable_state(self, api_client, test_user_credentials, test_user2_credentials):
        """GET /api/media/{id}/status - Returns correct viewable/expired status"""
        # User 1 uploads media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 checks status before viewing
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        status_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/status",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["expired"] is False
        assert data["is_viewable"] is True
        assert data["views_remaining"] == 1
        print("✓ Status shows viewable before viewing")
        
        # View the media
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        view_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/view?token={token_res.json()['access_token']}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res.status_code == 200
        
        # Check status after viewing
        status_res2 = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/status",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert status_res2.status_code == 200
        data2 = status_res2.json()
        assert data2["expired"] is True
        assert data2["is_viewable"] is False
        assert data2["views_remaining"] == 0
        print("✓ Status shows expired after viewing")

    def test_uploader_can_always_view_own_media(self, api_client, test_user_credentials):
        """GET /api/media/{id}/status - Uploader can always view their own media"""
        # User 1 uploads and views own media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # Check status as uploader
        status_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["views_remaining"] == -1  # Special value for uploader
        assert data["is_viewable"] is True
        
        # Get token as uploader (should always work)
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert token_res.status_code == 200
        assert token_res.json()["views_remaining"] == -1
        print("✓ Uploader can always view own media")


class TestMediaSecurity:
    """Test security features of ephemeral media"""

    def test_token_with_wrong_media_id_rejected(self, api_client, test_user_credentials, test_user2_credentials):
        """Security: Signed token with wrong media_id is rejected"""
        # User 1 uploads media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user_credentials)
        assert login_res.status_code == 200
        token1 = login_res.json()["token"]
        
        upload_res = api_client.post(
            f"{BASE_URL}/api/media/upload",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "content": SAMPLE_IMAGE_BASE64,
                "mime_type": "image/png",
                "view_limit": 1
            }
        )
        assert upload_res.status_code == 200
        media_id = upload_res.json()["media_id"]
        
        # User 2 gets token for this media
        login_res2 = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res2.status_code == 200
        token2 = login_res2.json()["token"]
        
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert token_res.status_code == 200
        access_token = token_res.json()["access_token"]
        
        # Try to use token with different media_id
        fake_media_id = "media_fakefakefake"
        view_res = api_client.get(
            f"{BASE_URL}/api/media/{fake_media_id}/view?token={access_token}",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert view_res.status_code == 401
        assert "does not match" in view_res.json()["detail"]
        print("✓ Token with wrong media_id rejected")

    def test_expired_media_blocks_all_token_requests(self, api_client, test_user_credentials, test_user2_credentials):
        """Security: After expiry, all token requests return 410"""
        # Use existing expired media
        media_id = "media_f3c1b7651354"
        
        # User 2 tries to get token for expired media
        login_res = api_client.post(f"{BASE_URL}/api/auth/login", json=test_user2_credentials)
        assert login_res.status_code == 200
        token = login_res.json()["token"]
        
        token_res = api_client.get(
            f"{BASE_URL}/api/media/{media_id}/token",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert token_res.status_code == 410
        assert "expired" in token_res.json()["detail"].lower()
        print("✓ Expired media blocks all token requests with 410")
