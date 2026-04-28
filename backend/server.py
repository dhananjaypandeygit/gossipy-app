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
import random
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

class ProximityJoin(BaseModel):
    latitude: float
    longitude: float
    radius: int = 500

class ProximityMessageCreate(BaseModel):
    room_id: str
    content: Optional[str] = None
    image: Optional[str] = None
    msg_type: str = "text"


# ============ HELPERS ============

# Anonymous name generator
_ANON_ADJECTIVES = [
    'Shadow', 'Cosmic', 'Neon', 'Phantom', 'Crystal', 'Midnight', 'Storm',
    'Velvet', 'Silent', 'Mystic', 'Lunar', 'Arctic', 'Blazing', 'Crimson',
    'Digital', 'Echo', 'Frost', 'Ghost', 'Haze', 'Jade', 'Nebula', 'Pixel',
    'Quantum', 'Rogue', 'Stealth', 'Thunder', 'Void', 'Whisper', 'Zen', 'Wild',
]
_ANON_NOUNS = [
    'Fox', 'Wolf', 'Hawk', 'Lynx', 'Panda', 'Tiger', 'Raven', 'Viper',
    'Falcon', 'Bear', 'Owl', 'Shark', 'Phoenix', 'Dragon', 'Cobra',
    'Panther', 'Eagle', 'Lion', 'Jaguar', 'Sphinx', 'Griffin', 'Kraken',
    'Cipher', 'Specter', 'Wraith', 'Ninja', 'Nomad', 'Drifter', 'Ranger', 'Scout',
]

def generate_anonymous_name() -> str:
    adj = random.choice(_ANON_ADJECTIVES)
    noun = random.choice(_ANON_NOUNS)
    num = random.randint(10, 99)
    return f"{adj}{noun}{num}"

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
    """Remove sensitive fields from user dict. Returns FULL user info (for self)."""
    u = {k: v for k, v in user.items() if k != '_id' and k != 'password_hash'}
    u['is_online'] = u.get('user_id', '') in online_users
    return u

def get_display_user(user: dict) -> dict:
    """Get user display info respecting anonymous mode. Use for OTHER users."""
    is_anon = user.get('is_anonymous', False)
    u = {
        'user_id': user.get('user_id', ''),
        'username': user.get('anonymous_username', 'Anonymous') if is_anon else user.get('username', ''),
        'avatar': None if is_anon else user.get('avatar'),
        'email': 'anonymous@gossipy.app' if is_anon else user.get('email', ''),
        'is_online': user.get('user_id', '') in online_users,
        'is_anonymous': is_anon,
        'last_seen': user.get('last_seen'),
    }
    return u

def get_sender_display(user: dict) -> dict:
    """Get sender info for messages. Bakes identity at send-time."""
    is_anon = user.get('is_anonymous', False)
    return {
        'sender_id': user.get('user_id', ''),
        'sender_username': user.get('anonymous_username', 'Anonymous') if is_anon else user.get('username', ''),
        'sender_avatar': None if is_anon else user.get('avatar'),
        'sender_is_anonymous': is_anon,
    }


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
        "is_anonymous": False,
        "anonymous_username": generate_anonymous_name(),
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
            "is_anonymous": False,
            "anonymous_username": generate_anonymous_name(),
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
    # Search by real username, email, OR anonymous_username
    users = await db.users.find(
        {
            "$and": [
                {"user_id": {"$ne": current_user["user_id"]}},
                {"$or": [
                    {"username": {"$regex": q, "$options": "i"}},
                    {"email": {"$regex": q, "$options": "i"}},
                    {"anonymous_username": {"$regex": q, "$options": "i"}},
                ]}
            ]
        },
        {"_id": 0, "password_hash": 0}
    ).to_list(20)
    # Apply display masking for anonymous users
    result = [get_display_user(u) for u in users]
    return {"users": result}

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

@fastapi_app.put("/api/users/anonymous")
async def toggle_anonymous(request: Request):
    """Toggle anonymous mode. Generates new anonymous username each time enabled."""
    current_user = await get_current_user(request)
    body = await request.json()
    enable = body.get("is_anonymous", False)

    update_doc = {"is_anonymous": enable}
    if enable:
        # Generate fresh anonymous name each time
        update_doc["anonymous_username"] = generate_anonymous_name()

    await db.users.update_one({"user_id": current_user["user_id"]}, {"$set": update_doc})
    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0, "password_hash": 0})
    user['is_online'] = user.get('user_id', '') in online_users
    return {"user": user}


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
            raw_user = await db.users.find_one(
                {"user_id": other_id[0]},
                {"_id": 0, "password_hash": 0, "location": 0, "location_updated_at": 0, "current_proximity_room": 0}
            )
            if raw_user:
                other_user = get_display_user(raw_user)

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
    sender_info = get_sender_display(current_user)
    message = {
        "message_id": msg_id,
        "conversation_id": body.conversation_id,
        "sender_id": current_user["user_id"],
        "sender_username": sender_info["sender_username"],
        "sender_avatar": sender_info["sender_avatar"],
        "sender_is_anonymous": sender_info["sender_is_anonymous"],
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

    # Calculate distance for each user and apply display masking
    result = []
    for u in nearby_users:
        loc = u.get("location", {})
        coords = loc.get("coordinates", [0, 0])
        distance = haversine_distance(latitude, longitude, coords[1], coords[0])
        display_u = get_display_user(u)
        display_u['distance_meters'] = round(distance, 1)
        result.append(display_u)

    # Sort by distance
    result.sort(key=lambda x: x.get('distance_meters', 0))

    return {"users": result, "radius": radius, "count": len(result)}


# ============ GEOHASH IMPLEMENTATION ============

_BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz'

def encode_geohash(latitude: float, longitude: float, precision: int = 7) -> str:
    """Encode lat/lng to geohash string at given precision."""
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    geohash = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True
    while len(geohash) < precision:
        if even:
            mid = (lon_range[0] + lon_range[1]) / 2
            if longitude >= mid:
                ch |= bits[bit]
                lon_range[0] = mid
            else:
                lon_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if latitude >= mid:
                ch |= bits[bit]
                lat_range[0] = mid
            else:
                lat_range[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(_BASE32[ch])
            bit = 0
            ch = 0
    return ''.join(geohash)

# Radius → geohash precision mapping
RADIUS_TO_PRECISION = {
    10: 8,   # ~38m × 19m cells
    50: 7,   # ~150m × 150m cells
    100: 6,  # ~610m × 610m cells
    500: 5,  # ~4.9km × 4.9km cells
}

def get_room_id(latitude: float, longitude: float, radius: int) -> str:
    """Generate a proximity room ID based on geohash + radius."""
    precision = RADIUS_TO_PRECISION.get(radius, 5)
    gh = encode_geohash(latitude, longitude, precision)
    return f"prox_{gh}_{radius}m"


# ============ PROXIMITY CHAT ROUTES ============

# Track sid -> proximity room mapping for auto-leave
sid_to_proximity_room = {}

@fastapi_app.post("/api/proximity/join")
async def join_proximity_room(request: Request, body: ProximityJoin):
    """Join a proximity chat room based on current location and radius."""
    current_user = await get_current_user(request)
    
    valid_radii = [10, 50, 100, 500]
    radius = body.radius if body.radius in valid_radii else 500
    
    room_id = get_room_id(body.latitude, body.longitude, radius)
    geohash = encode_geohash(body.latitude, body.longitude, RADIUS_TO_PRECISION.get(radius, 5))
    
    # Upsert the room
    now_iso = datetime.now(timezone.utc).isoformat()
    room = await db.proximity_rooms.find_one({"room_id": room_id}, {"_id": 0})
    
    if room:
        # Add participant if not already in
        if current_user["user_id"] not in room.get("participants", []):
            await db.proximity_rooms.update_one(
                {"room_id": room_id},
                {
                    "$addToSet": {"participants": current_user["user_id"]},
                    "$set": {"updated_at": now_iso}
                }
            )
    else:
        room = {
            "room_id": room_id,
            "geohash": geohash,
            "radius": radius,
            "center_lat": body.latitude,
            "center_lng": body.longitude,
            "participants": [current_user["user_id"]],
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await db.proximity_rooms.insert_one(room)
    
    # Also update the user's location
    location_doc = {
        "type": "Point",
        "coordinates": [body.longitude, body.latitude]
    }
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {
            "location": location_doc,
            "location_updated_at": now_iso,
            "current_proximity_room": room_id,
        }}
    )
    
    # Get updated room with participant info
    updated_room = await db.proximity_rooms.find_one({"room_id": room_id}, {"_id": 0})
    participant_count = len(updated_room.get("participants", []))
    
    # Notify room about new member via socket
    user_info = {"user_id": current_user["user_id"], "username": current_user.get("username")}
    await sio.emit('proximity_user_joined', {
        "room_id": room_id,
        "user": user_info,
        "participant_count": participant_count,
    }, room=room_id)
    
    return {
        "room_id": room_id,
        "geohash": geohash,
        "radius": radius,
        "participant_count": participant_count,
    }

@fastapi_app.post("/api/proximity/leave")
async def leave_proximity_room(request: Request):
    """Leave current proximity chat room."""
    current_user = await get_current_user(request)
    body = await request.json()
    room_id = body.get("room_id")
    
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id required")
    
    # Remove from participants
    await db.proximity_rooms.update_one(
        {"room_id": room_id},
        {"$pull": {"participants": current_user["user_id"]}}
    )
    
    # Clear user's current room
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$unset": {"current_proximity_room": ""}}
    )
    
    # Get updated count
    room = await db.proximity_rooms.find_one({"room_id": room_id}, {"_id": 0})
    participant_count = len(room.get("participants", [])) if room else 0
    
    # Remove room if empty
    if participant_count == 0 and room:
        await db.proximity_rooms.delete_one({"room_id": room_id})
    
    # Notify room
    await sio.emit('proximity_user_left', {
        "room_id": room_id,
        "user_id": current_user["user_id"],
        "username": current_user.get("username"),
        "participant_count": participant_count,
    }, room=room_id)
    
    return {"success": True, "participant_count": participant_count}

@fastapi_app.get("/api/proximity/room/{room_id}")
async def get_proximity_room(request: Request, room_id: str):
    """Get proximity room info with participant details."""
    current_user = await get_current_user(request)
    room = await db.proximity_rooms.find_one({"room_id": room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Get participant info
    participants = []
    for pid in room.get("participants", []):
        u = await db.users.find_one({"user_id": pid}, {"_id": 0, "password_hash": 0, "location": 0})
        if u:
            participants.append(get_display_user(u))
    
    return {
        "room": {
            "room_id": room["room_id"],
            "geohash": room.get("geohash"),
            "radius": room.get("radius"),
            "participant_count": len(participants),
            "created_at": room.get("created_at"),
        },
        "participants": participants,
    }

@fastapi_app.get("/api/proximity/messages/{room_id}")
async def get_proximity_messages(request: Request, room_id: str, skip: int = 0, limit: int = 50):
    """Get messages for a proximity room (only non-expired)."""
    current_user = await get_current_user(request)
    
    # Only show messages from last 24 hours
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    
    messages = await db.proximity_messages.find(
        {"room_id": room_id, "created_at": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    messages.reverse()
    
    return {"messages": messages}

@fastapi_app.post("/api/proximity/messages")
async def send_proximity_message(request: Request, body: ProximityMessageCreate):
    """Send a message to a proximity room (REST fallback)."""
    current_user = await get_current_user(request)
    
    # Verify room exists
    room = await db.proximity_rooms.find_one({"room_id": body.room_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Verify user is participant
    if current_user["user_id"] not in room.get("participants", []):
        raise HTTPException(status_code=403, detail="Not a room participant")
    
    msg_id = generate_id("pmsg_")
    now_iso = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    
    full_user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0, "password_hash": 0})
    sender_info = get_sender_display(full_user) if full_user else get_sender_display(current_user)
    
    message = {
        "message_id": msg_id,
        "room_id": body.room_id,
        "sender_id": current_user["user_id"],
        "sender_username": sender_info["sender_username"],
        "sender_avatar": sender_info["sender_avatar"],
        "sender_is_anonymous": sender_info["sender_is_anonymous"],
        "content": body.content,
        "image": body.image,
        "msg_type": body.msg_type,
        "created_at": now_iso,
        "expires_at": expires_at,
    }
    await db.proximity_messages.insert_one(message)
    
    msg_copy = {k: v for k, v in message.items() if k != '_id'}
    
    # Update room activity
    await db.proximity_rooms.update_one(
        {"room_id": body.room_id},
        {"$set": {"updated_at": now_iso, "last_message": body.content or "Image"}}
    )
    
    # Broadcast via socket
    await sio.emit('proximity_message', msg_copy, room=body.room_id)
    
    return {"message": msg_copy}


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

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    sender_info = get_sender_display(user) if user else {"sender_id": user_id, "sender_username": "", "sender_avatar": None, "sender_is_anonymous": False}

    msg_id = generate_id("msg_")
    message = {
        "message_id": msg_id,
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "sender_username": sender_info["sender_username"],
        "sender_avatar": sender_info["sender_avatar"],
        "sender_is_anonymous": sender_info["sender_is_anonymous"],
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
async def join_proximity(sid, data):
    """Join a proximity chat room via WebSocket."""
    user_id = sid_to_user.get(sid)
    if not user_id:
        return
    room_id = data.get('room_id')
    if not room_id:
        return

    # Leave previous proximity room if any
    old_room = sid_to_proximity_room.get(sid)
    if old_room and old_room != room_id:
        await sio.leave_room(sid, old_room)
        # Remove from old room participants
        await db.proximity_rooms.update_one(
            {"room_id": old_room},
            {"$pull": {"participants": user_id}}
        )
        old_room_doc = await db.proximity_rooms.find_one({"room_id": old_room}, {"_id": 0})
        old_count = len(old_room_doc.get("participants", [])) if old_room_doc else 0
        if old_count == 0 and old_room_doc:
            await db.proximity_rooms.delete_one({"room_id": old_room})
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
        await sio.emit('proximity_user_left', {
            "room_id": old_room,
            "user_id": user_id,
            "username": user.get("username", "") if user else "",
            "participant_count": old_count,
        }, room=old_room)

    await sio.enter_room(sid, room_id)
    sid_to_proximity_room[sid] = room_id

    # Add to room participants
    await db.proximity_rooms.update_one(
        {"room_id": room_id},
        {"$addToSet": {"participants": user_id}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    room = await db.proximity_rooms.find_one({"room_id": room_id}, {"_id": 0})
    count = len(room.get("participants", [])) if room else 1
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})

    await sio.emit('proximity_user_joined', {
        "room_id": room_id,
        "user": {"user_id": user_id, "username": user.get("username", "") if user else ""},
        "participant_count": count,
    }, room=room_id)
    logger.info(f"Socket {sid} joined proximity room {room_id}")

@sio.event
async def leave_proximity(sid, data):
    """Leave a proximity chat room via WebSocket."""
    user_id = sid_to_user.get(sid)
    if not user_id:
        return
    room_id = data.get('room_id') or sid_to_proximity_room.get(sid)
    if not room_id:
        return

    await sio.leave_room(sid, room_id)
    sid_to_proximity_room.pop(sid, None)

    await db.proximity_rooms.update_one(
        {"room_id": room_id},
        {"$pull": {"participants": user_id}}
    )
    await db.users.update_one(
        {"user_id": user_id},
        {"$unset": {"current_proximity_room": ""}}
    )
    room = await db.proximity_rooms.find_one({"room_id": room_id}, {"_id": 0})
    count = len(room.get("participants", [])) if room else 0
    if count == 0 and room:
        await db.proximity_rooms.delete_one({"room_id": room_id})
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    await sio.emit('proximity_user_left', {
        "room_id": room_id,
        "user_id": user_id,
        "username": user.get("username", "") if user else "",
        "participant_count": count,
    }, room=room_id)

@sio.event
async def send_proximity_message(sid, data):
    """Send message to proximity room via socket."""
    user_id = sid_to_user.get(sid)
    if not user_id:
        return
    room_id = data.get('room_id')
    content = data.get('content')
    image = data.get('image')
    msg_type = data.get('msg_type', 'text')

    if not room_id:
        return

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    sender_info = get_sender_display(user) if user else {"sender_id": user_id, "sender_username": "", "sender_avatar": None, "sender_is_anonymous": False}
    msg_id = generate_id("pmsg_")
    now_iso = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    message = {
        "message_id": msg_id,
        "room_id": room_id,
        "sender_id": user_id,
        "sender_username": sender_info["sender_username"],
        "sender_avatar": sender_info["sender_avatar"],
        "sender_is_anonymous": sender_info["sender_is_anonymous"],
        "content": content,
        "image": image,
        "msg_type": msg_type,
        "created_at": now_iso,
        "expires_at": expires_at,
    }
    await db.proximity_messages.insert_one(message)

    await db.proximity_rooms.update_one(
        {"room_id": room_id},
        {"$set": {"updated_at": now_iso, "last_message": content or "Image"}}
    )

    msg_copy = {k: v for k, v in message.items() if k != '_id'}
    await sio.emit('proximity_message', msg_copy, room=room_id)

@sio.event
async def disconnect(sid):
    user_id = sid_to_user.pop(sid, None)

    # Auto-leave proximity room on disconnect
    prox_room = sid_to_proximity_room.pop(sid, None)
    if prox_room and user_id:
        await db.proximity_rooms.update_one(
            {"room_id": prox_room},
            {"$pull": {"participants": user_id}}
        )
        await db.users.update_one(
            {"user_id": user_id},
            {"$unset": {"current_proximity_room": ""}}
        )
        room = await db.proximity_rooms.find_one({"room_id": prox_room}, {"_id": 0})
        count = len(room.get("participants", [])) if room else 0
        if count == 0 and room:
            await db.proximity_rooms.delete_one({"room_id": prox_room})
        await sio.emit('proximity_user_left', {
            "room_id": prox_room,
            "user_id": user_id,
            "username": "",
            "participant_count": count,
        }, room=prox_room)

    if user_id and user_id in online_users:
        online_users[user_id].discard(sid)
        if not online_users[user_id]:
            del online_users[user_id]
            last_seen_iso = datetime.now(timezone.utc).isoformat()
            await db.users.update_one({"user_id": user_id}, {"$set": {
                "is_online": False,
                "last_seen": last_seen_iso
            }})
            await sio.emit('user_offline', {'user_id': user_id, 'last_seen': last_seen_iso})
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
    # Proximity chat indexes
    await db.proximity_rooms.create_index("room_id", unique=True)
    await db.proximity_rooms.create_index("geohash")
    await db.proximity_messages.create_index("room_id")
    await db.proximity_messages.create_index("message_id", unique=True)
    # TTL index: auto-delete messages after 24 hours
    await db.proximity_messages.create_index("expires_at", expireAfterSeconds=0)
    logger.info("Database indexes created (including 2dsphere + proximity TTL)")

@fastapi_app.on_event("shutdown")
async def shutdown():
    client.close()


# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')
app = socket_app
