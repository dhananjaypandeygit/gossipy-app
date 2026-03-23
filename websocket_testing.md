# WebSocket Test Suite

## Required Test Implementation

Use `python-socketio` client to connect and test Socket.IO functionality.

### Backend URL: https://jwt-chat-core.preview.emergentagent.com
### Socket Path: /api/socket.io

### 1. Connection Lifecycle Testing
- Test successful connection to `/api/socket.io`
- Test disconnect event fires correctly

### 2. Room Management Testing
- Test `join_room` event with valid room_id
- Test multiple clients in same room

### 3. Broadcasting & Real-time Sync Testing
- Test messages received by all clients in same room
- Test messages NOT received by clients in different rooms

### 4. Error Handling Testing
- Test malformed data handling
- Test rapid connect/disconnect cycles

### 5. Multi-user Chat Testing
- Test 2 users in same conversation receive each other's messages
- Test typing indicators broadcast correctly
