# Gossipy Chat - Product Requirements Document

## Overview
Gossipy is a real-time 1-to-1 private messaging app with proximity-based user discovery, built with React Native (Expo), Python FastAPI, Socket.IO, and MongoDB. It features a dark "Bioluminescent Deep Sea" theme with neon cyan accents.

## Core Features

### Authentication
- **Email/Password Auth**: JWT-based signup and login
- **Google OAuth**: Emergent-managed Google social login via `auth.emergentagent.com`
- **Session Management**: JWT tokens stored in AsyncStorage, 7-day expiry

### Chat System
- **1-to-1 Private Chat**: Direct messaging between users
- **Real-time Messaging**: Socket.IO WebSocket for instant delivery
- **Text Messages**: Standard text messaging with 2000 char limit
- **Image Sharing**: Send images (captured as base64) in conversations
- **Typing Indicators**: Live "user is typing..." feedback
- **Read Receipts**: Double-check marks for read messages
- **Online Status**: Green dot indicator for online users

### User Profile
- **Username**: Editable display name
- **Avatar Upload**: Image picker for profile pictures (base64 storage)
- **User Search**: Find users by username or email

### Geolocation & Proximity
- **Location Tracking**: Battery-optimized via `expo-location` (Balanced accuracy, 10m distance interval, 30s time interval)
- **Nearby Users**: Discover users within 10m, 50m, 100m, or 500m radius
- **MongoDB 2dsphere**: GeoJSON Point storage with `$nearSphere` queries
- **Real-time Location**: Updates via Socket.IO (throttled to max 1 per 15 seconds)
- **Privacy**: Only distance shown to other users, raw coordinates never exposed

### Proximity Chat System
- **GeoHash-based Rooms**: Dynamic room creation using geohash clustering (precision: 10m→8, 50m→7, 100m→6, 500m→5)
- **Room ID Format**: `prox_{geohash}_{radius}m` — users at same location+radius auto-join same room
- **24-Hour Message Expiry**: MongoDB TTL index auto-deletes messages after 24 hours
- **Real-time Group Chat**: Socket.IO broadcast to all room participants
- **Auto Join/Leave**: Users auto-leave rooms on disconnect, rooms auto-delete when empty
- **System Notifications**: Join/leave events broadcast as system messages

### Real-time User Presence
- **Global Presence Map**: AuthContext maintains `Record<user_id, {is_online, last_seen}>` via Socket.IO events
- **Instant Updates**: `user_online` / `user_offline` events broadcast to all connected clients (no polling)
- **Last Seen Formatting**: "Just now", "5m ago", "2h ago", "Yesterday", "3d ago"
- **Efficient**: No API re-fetch needed — presence state updates via WebSocket only
- **Chat Header**: Real-time "Online" / "last seen Xm ago" / "typing..." priority stack
- **Chats List**: Green dot + "Online" text for online users, last seen text for offline

### Anonymous Mode (Ghost Mode)
- **Toggle**: `PUT /api/users/anonymous` — enables/disables anonymous identity
- **Random Names**: Fun adjective+noun+number combos (e.g., ShadowWolf20, VoidFalcon54)
- **New Name Per Enable**: Each toggle ON generates a fresh anonymous name
- **Privacy Protection**: When anonymous, all APIs mask real name, email (→ anonymous@gossipy.app), and avatar (→ null)
- **Send-time Baking**: Messages store sender_username/avatar/is_anonymous at creation — identity changes don't retroactively affect old messages
- **Frontend**: "Ghost Mode" toggle on Profile with protection checklist (real name, avatar, email all hidden)

## Tech Stack
- **Frontend**: React Native + Expo SDK 54 + Expo Router
- **Backend**: Python FastAPI + python-socketio
- **Database**: MongoDB (Motor async driver)
- **Real-time**: Socket.IO (WebSocket + polling fallback)
- **Auth**: JWT (PyJWT) + Emergent Google OAuth

## API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/signup | Register with email/password |
| POST | /api/auth/login | Login with email/password |
| GET | /api/auth/session | Exchange Google OAuth session_id |
| GET | /api/auth/me | Get current user |
| POST | /api/auth/logout | Logout |
| GET | /api/users/search | Search users |
| PUT | /api/users/profile | Update profile |
| POST | /api/users/avatar | Upload avatar |
| GET | /api/conversations | List conversations |
| POST | /api/conversations | Create conversation |
| GET | /api/conversations/{id}/messages | Get messages |
| PUT | /api/users/location | Update user GeoJSON location |
| GET | /api/users/nearby | Find nearby users by radius |
| POST | /api/messages | Send message (REST) |
| POST | /api/messages/read | Mark messages read |

## Socket.IO Events
| Event | Direction | Description |
|-------|-----------|-------------|
| authenticate | Client → Server | Auth with JWT token |
| join_conversation | Client → Server | Join chat room |
| send_message | Client → Server | Send message |
| typing | Client → Server | Typing indicator |
| new_message | Server → Client | New message broadcast |
| user_typing | Server → Client | Typing status |
| messages_read | Server → Client | Read receipt |
| user_online/offline | Server → Client | Presence updates |

## Screen Hierarchy
1. **/** - Auth screen (login/signup + Google) - "Gossipy" branding
2. **/oauth-callback** - Google OAuth callback handler
3. **/(app)/chats** - Conversations list (Tab 1)
4. **/(app)/nearby** - Nearby users with radius selector (Tab 2)
5. **/(app)/profile** - User profile (Tab 3)
6. **/(app)/chat/[id]** - Individual chat screen

## Database Collections
- `users` - user_id, email, username, password_hash, avatar, is_online, last_seen
- `user_sessions` - session_token, user_id, expires_at
- `conversations` - conversation_id, participants[], last_message, updated_at
- `messages` - message_id, conversation_id, sender_id, content, image, msg_type, read, created_at

## Design System
- **Theme**: Dark mode "Bioluminescent Deep Sea"
- **Primary BG**: #050505 (Deep Obsidian)
- **Accent**: #00F0FF (Neon Cyan)
- **Chat Bubbles**: #2563EB (mine) / #1E293B (theirs)
- **Typography**: System font, bold headings
- **Components**: Pill buttons, floating inputs, squircle avatars
