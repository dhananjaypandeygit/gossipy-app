import socketio
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import base64
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT secret
JWT_SECRET = os.environ.get('JWT_SECRET', 'neonvoid_chat_secret_key_2024_xtra_secure_padding')
JWT_ALGORITHM = 'HS256'

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', logger=False, engineio_logger=False)

# FastAPI app
fastapi_app = FastAPI()

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track online users: user_id -> set of sids
online_users = {}
# Track sid -> user_id mapping
sid_to_user = {}


# ============ PYDANTIC MODELS ============

class SignupRequest(BaseModel):
    email: str
    username: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ProfileUpdate(BaseModel):
    username: Optional[str] = None
    avatar: Optional[str] = None

class ConversationCreate(BaseModel):
    participant_id: str

class MessageCreate(BaseModel):
    conversation_id: str
    content: Optional[str] = None
    image: Optional[str] = None
    msg_type: str = "text"

class LocationUpdate(BaseModel):
    latitude: float
    longitude: float

class NearbyQuery(BaseModel):
    latitude: float
    longitude: float
    radius: int = 500  # meters: 10, 50, 100, 500


# ============ HELPERS ============

def generate_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str) -> str:
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=7),
        'iat': datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    # Check Authorization header
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    # Check cookies
    if not token:
        token = request.cookies.get('session_token')
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # First try JWT decode
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop('password_hash', None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        pass

    # Fallback: check session_token in DB (for Google OAuth)
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")
    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user.pop('password_hash', None)
    return user


def serialize_user(user: dict) -> dict:
    """Remove sensitive fields from user dict."""
    u = {k: v for k, v in user.items() if k != '_id' and k != 'password_hash'}
    u['is_online'] = u.get('user_id', '') in online_users
    return u


# ============ AUTH ROUTES ============

@fastapi_app.post("/api/auth/signup")
async def signup(req: SignupRequest):
    existing = await db.users.find_one({"email": req.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_username = await db.users.find_one({"username": req.username}, {"_id": 0})
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")

    user_id = generate_id("user_")
    user_doc = {
        "user_id": user_id,
        "email": req.email,
        "username": req.username,
        "password_hash": hash_password(req.password),
        "avatar": None,
        "is_online": False,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)
    token = create_token(user_id)
    return {
        "token": token,
        "user": serialize_user(user_doc)
    }

@fastapi_app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = await db.users.find_one({"email": req.email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get('password_hash'):
        raise HTTPException(status_code=401, detail="Please login with Google")
    if not verify_password(req.password, user['password_hash']):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Update last_seen
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_seen": datetime.now(timezone.utc).isoformat()}})
    token = create_token(user["user_id"])
    return {
        "token": token,
        "user": serialize_user(user)
    }

# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
@fastapi_app.get("/api/auth/session")
async def exchange_session(session_id: str, response: Response):
    """Exchange Emergent OAuth session_id for a session token."""
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id}
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session")
    data = resp.json()

    email = data.get("email")
    name = data.get("name", "")
    picture = data.get("picture", "")
    session_token = data.get("session_token", "")

    # Find or create user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {
            "avatar": picture or existing.get("avatar"),
            "last_seen": datetime.now(timezone.utc).isoformat()
        }})
    else:
        user_id = generate_id("user_")
        user_doc = {
            "user_id": user_id,
            "email": email,
            "username": name or email.split("@")[0],
            "password_hash": None,
            "avatar": picture,
            "is_online": False,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user_doc)

    # Store session
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 3600
    )

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    jwt_token = create_token(user_id)
    return {
        "token": jwt_token,
        "user": serialize_user(user)
    }

@fastapi_app.get("/api/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    return {"user": user}

@fastapi_app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get('session_token')
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"message": "Logged out"}


# ============ USER ROUTES ============

@fastapi_app.get("/api/users/search")
async def search_users(request: Request, q: str = ""):
    current_user = await get_current_user(request)
    if not q or len(q) < 1:
        return {"users": []}
    users = await db.users.find(
        {
            "$and": [
                {"user_id": {"$ne": current_user["user_id"]}},
                {"$or": [
                    {"username": {"$regex": q, "$options": "i"}},
                    {"email": {"$regex": q, "$options": "i"}}
                ]}
            ]
        },
        {"_id": 0, "password_hash": 0}
    ).to_list(20)
    for u in users:
        u['is_online'] = u.get('user_id', '') in online_users
    return {"users": users}

@fastapi_app.put("/api/users/profile")
async def update_profile(request: Request, update: ProfileUpdate):
    current_user = await get_current_user(request)
    update_dict = {}
    if update.username:
        existing = await db.users.find_one(
            {"username": update.username, "user_id": {"$ne": current_user["user_id"]}},
            {"_id": 0}
        )
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        update_dict["username"] = update.username
    if update.avatar is not None:
        update_dict["avatar"] = update.avatar
    if update_dict:
        await db.users.update_one({"user_id": current_user["user_id"]}, {"$set": update_dict})
    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0, "password_hash": 0})
    user['is_online'] = user.get('user_id', '') in online_users
    return {"user": user}

@fastapi_app.post("/api/users/avatar")
async def upload_avatar(request: Request):
    current_user = await get_current_user(request)
    body = await request.json()
    avatar_base64 = body.get("avatar")
    if not avatar_base64:
        raise HTTPException(status_code=400, detail="No avatar data")
    await db.users.update_one({"user_id": current_user["user_id"]}, {"$set": {"avatar": avatar_base64}})
    return {"avatar": avatar_base64}


# ============ CONVERSATION ROUTES ============

@fastapi_app.get("/api/conversations")
async def get_conversations(request: Request):
    current_user = await get_current_user(request)
    conversations = await db.conversations.find(
        {"participants": current_user["user_id"]},
        {"_id": 0}
    ).sort("updated_at", -1).to_list(100)

    result = []
    for conv in conversations:
        other_id = [p for p in conv["participants"] if p != current_user["user_id"]]
        other_user = None
        if other_id:
            other_user = await db.users.find_one({"user_id": other_id[0]}, {"_id": 0, "password_hash": 0})
            if other_user:
                other_user['is_online'] = other_user.get('user_id', '') in online_users

        # Count unread messages
        unread = await db.messages.count_documents({
            "conversation_id": conv["conversation_id"],
            "sender_id": {"$ne": current_user["user_id"]},
            "read": False
        })

        result.append({
            **conv,
            "other_user": other_user,
            "unread_count": unread
        })
    return {"conversations": result}

@fastapi_app.post("/api/conversations")
async def create_conversation(request: Request, body: ConversationCreate):
    current_user = await get_current_user(request)
    participant_id = body.participant_id

    # Check if conversation already exists
    existing = await db.conversations.find_one({
        "participants": {"$all": [current_user["user_id"], participant_id], "$size": 2}
    }, {"_id": 0})
    if existing:
        return {"conversation": existing}

    # Verify participant exists
    other_user = await db.users.find_one({"user_id": participant_id}, {"_id": 0})
    if not other_user:
        raise HTTPException(status_code=404, detail="User not found")

    conv_id = generate_id("conv_")
    conversation = {
        "conversation_id": conv_id,
        "participants": [current_user["user_id"], participant_id],
        "last_message": None,
        "last_message_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.conversations.insert_one(conversation)
    conv_copy = {k: v for k, v in conversation.items() if k != '_id'}
    return {"conversation": conv_copy}


@fastapi_app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(request: Request, conversation_id: str, skip: int = 0, limit: int = 50):
    current_user = await get_current_user(request)
    # Verify user is participant
    conv = await db.conversations.find_one({
        "conversation_id": conversation_id,
        "participants": current_user["user_id"]
    }, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await db.messages.find(
        {"conversation_id": conversation_id},
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    messages.reverse()

    # Mark messages as read
    await db.messages.update_many(
        {
            "conversation_id": conversation_id,
            "sender_id": {"$ne": current_user["user_id"]},
            "read": False
        },
        {"$set": {"read": True}}
    )

    return {"messages": messages}


@fastapi_app.post("/api/messages")
async def send_message_rest(request: Request, body: MessageCreate):
    current_user = await get_current_user(request)
    # Verify user is participant
    conv = await db.conversations.find_one({
        "conversation_id": body.conversation_id,
        "participants": current_user["user_id"]
    }, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_id = generate_id("msg_")
    message = {
        "message_id": msg_id,
        "conversation_id": body.conversation_id,
        "sender_id": current_user["user_id"],
        "content": body.content,
        "image": body.image,
        "msg_type": body.msg_type,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.messages.insert_one(message)

    # Update conversation
    last_msg_text = body.content if body.content else "Image"
    await db.conversations.update_one(
        {"conversation_id": body.conversation_id},
        {"$set": {
            "last_message": last_msg_text,
            "last_message_at": message["created_at"],
            "updated_at": message["created_at"]
        }}
    )

    msg_copy = {k: v for k, v in message.items() if k != '_id'}

    # Broadcast via socket
    await sio.emit('new_message', msg_copy, room=body.conversation_id)

    return {"message": msg_copy}


@fastapi_app.post("/api/messages/read")
async def mark_messages_read(request: Request):
    current_user = await get_current_user(request)
    body = await request.json()
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id required")

    await db.messages.update_many(
        {
            "conversation_id": conversation_id,
            "sender_id": {"$ne": current_user["user_id"]},
            "read": False
        },
        {"$set": {"read": True}}
    )

    # Notify the other user their messages were read
    await sio.emit('messages_read', {
        "conversation_id": conversation_id,
        "reader_id": current_user["user_id"]
    }, room=conversation_id)

    return {"success": True}


# ============ HEALTH CHECK ============

@fastapi_app.get("/api")
async def root():
    return {"message": "Gossipy Chat API", "status": "online"}


# ============ LOCATION / NEARBY ROUTES ============

import math

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two lat/lon points."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@fastapi_app.put("/api/users/location")
async def update_location(request: Request, body: LocationUpdate):
    """Update user's current location. Stored as GeoJSON for geospatial queries."""
    current_user = await get_current_user(request)
    location_doc = {
        "type": "Point",
        "coordinates": [body.longitude, body.latitude]  # GeoJSON: [lng, lat]
    }
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {
            "location": location_doc,
            "location_updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    return {"success": True, "location": {"latitude": body.latitude, "longitude": body.longitude}}

@fastapi_app.get("/api/users/nearby")
async def get_nearby_users(request: Request, latitude: float, longitude: float, radius: int = 500):
    """Find nearby users within given radius (meters). Uses MongoDB 2dsphere index."""
    current_user = await get_current_user(request)

    # Validate radius
    valid_radii = [10, 50, 100, 500]
    if radius not in valid_radii:
        radius = min(valid_radii, key=lambda x: abs(x - radius))

    # MongoDB $nearSphere query with $maxDistance in meters
    try:
        users_cursor = db.users.find(
            {
                "user_id": {"$ne": current_user["user_id"]},
                "location": {
                    "$nearSphere": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [longitude, latitude]
                        },
                        "$maxDistance": radius
                    }
                }
            },
            {"_id": 0, "password_hash": 0}
        ).limit(50)
        nearby_users = await users_cursor.to_list(50)
    except Exception as e:
        logger.error(f"Nearby query error: {e}")
        nearby_users = []

    # Calculate distance for each user and add online status
    result = []
    for u in nearby_users:
        loc = u.get("location", {})
        coords = loc.get("coordinates", [0, 0])
        distance = haversine_distance(latitude, longitude, coords[1], coords[0])
        u['distance_meters'] = round(distance, 1)
        u['is_online'] = u.get('user_id', '') in online_users
        # Remove location for privacy (only show distance)
        u.pop('location', None)
        u.pop('location_updated_at', None)
        result.append(u)

    # Sort by distance
    result.sort(key=lambda x: x.get('distance_meters', 0))

    return {"users": result, "radius": radius, "count": len(result)}


# ============ SOCKET.IO EVENTS ============

@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")

@sio.event
async def authenticate(sid, data):
    """Authenticate socket connection with JWT token."""
    token = data.get('token', '')
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not user:
            await sio.emit('auth_error', {'error': 'User not found'}, to=sid)
            return

        sid_to_user[sid] = user_id
        if user_id not in online_users:
            online_users[user_id] = set()
        online_users[user_id].add(sid)

        await db.users.update_one({"user_id": user_id}, {"$set": {"is_online": True}})
        await sio.emit('authenticated', {'user_id': user_id}, to=sid)

        # Notify all about user online
        await sio.emit('user_online', {'user_id': user_id})
        logger.info(f"User {user_id} authenticated via socket {sid}")
    except Exception as e:
        logger.error(f"Socket auth error: {e}")
        await sio.emit('auth_error', {'error': str(e)}, to=sid)

@sio.event
async def join_conversation(sid, data):
    """Join a conversation room."""
    conversation_id = data.get('conversation_id')
    if not conversation_id:
        return
    await sio.enter_room(sid, conversation_id)
    logger.info(f"Socket {sid} joined room {conversation_id}")

@sio.event
async def leave_conversation(sid, data):
    """Leave a conversation room."""
    conversation_id = data.get('conversation_id')
    if not conversation_id:
        return
    await sio.leave_room(sid, conversation_id)

@sio.event
async def send_message(sid, data):
    """Handle sending a message via socket."""
    user_id = sid_to_user.get(sid)
    if not user_id:
        return

    conversation_id = data.get('conversation_id')
    content = data.get('content')
    image = data.get('image')
    msg_type = data.get('msg_type', 'text')

    if not conversation_id:
        return

    msg_id = generate_id("msg_")
    message = {
        "message_id": msg_id,
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "content": content,
        "image": image,
        "msg_type": msg_type,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.messages.insert_one(message)

    last_msg_text = content if content else "Image"
    await db.conversations.update_one(
        {"conversation_id": conversation_id},
        {"$set": {
            "last_message": last_msg_text,
            "last_message_at": message["created_at"],
            "updated_at": message["created_at"]
        }}
    )

    msg_copy = {k: v for k, v in message.items() if k != '_id'}
    await sio.emit('new_message', msg_copy, room=conversation_id)

@sio.event
async def typing(sid, data):
    """Handle typing indicator."""
    user_id = sid_to_user.get(sid)
    if not user_id:
        return
    conversation_id = data.get('conversation_id')
    is_typing = data.get('is_typing', False)
    if conversation_id:
        await sio.emit('user_typing', {
            'user_id': user_id,
            'conversation_id': conversation_id,
            'is_typing': is_typing
        }, room=conversation_id, skip_sid=sid)

@sio.event
async def update_location(sid, data):
    """Handle location update via socket for real-time nearby detection."""
    user_id = sid_to_user.get(sid)
    if not user_id:
        return
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    if latitude is None or longitude is None:
        return
    location_doc = {
        "type": "Point",
        "coordinates": [longitude, latitude]
    }
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "location": location_doc,
            "location_updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

@sio.event
async def disconnect(sid):
    user_id = sid_to_user.pop(sid, None)
    if user_id and user_id in online_users:
        online_users[user_id].discard(sid)
        if not online_users[user_id]:
            del online_users[user_id]
            await db.users.update_one({"user_id": user_id}, {"$set": {
                "is_online": False,
                "last_seen": datetime.now(timezone.utc).isoformat()
            }})
            await sio.emit('user_offline', {'user_id': user_id})
    logger.info(f"Client disconnected: {sid}")


# ============ DATABASE INDEXES ============

@fastapi_app.on_event("startup")
async def startup():
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username")
    await db.users.create_index([("location", "2dsphere")])
    await db.user_sessions.create_index("session_token", unique=True)
    await db.conversations.create_index("conversation_id", unique=True)
    await db.conversations.create_index("participants")
    await db.messages.create_index("conversation_id")
    await db.messages.create_index("message_id", unique=True)
    logger.info("Database indexes created (including 2dsphere)")

@fastapi_app.on_event("shutdown")
async def shutdown():
    client.close()


# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
app = socket_app
