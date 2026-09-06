import os
import io
import jwt
import time
import uuid
import json
import sqlite3
import hashlib
import requests
import base64
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, g
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ─── APP INITIALIZATION & ENV CONFIG ─────────────────────────────────────────
app = Flask(__name__)

# Load configurations from environment variables or use fallback defaults
PLAYFAB_TITLE_ID = "AB44B"
PLAYFAB_SECRET_KEY = "QZ7OIEIZD3PKD6OOWAGJCKD6JFUIYGE8GS1FZEKAU7Y6PKOFEK"
META_ACCESS_TOKEN = "OC|1262483513615215|4b731bfc16926703cec22d9c8313c830"
EVENT_LOG_DIR = "/tmp/eventlogs"
LOG_DIR = "/tmp/logs"
SQLITE_DB_PATH = "/tmp/mothership.db"
# ─── CRYPTOGRAPHIC KEYS SETUP (ECDSA ES256) ──────────────────────────────────
# Load ES256 keys. If missing in env, dynamically generate standard keys for runtime fallback.
private_key_pem = os.environ.get("MOTHERSHIP_PRIVATE_KEY")
if private_key_pem:
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'),
        password=None
    )
else:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

public_key = private_key.public_key()

# ─── LOCAL IN-MEMORY STORES ──────────────────────────────────────────────────
pending_nonces = {}
active_player_sessions = set()
rate_limit_store = {}

# ─── DATA LOADING HELPER ─────────────────────────────────────────────────────
def load_data_file(filename, default_payload):
    paths = [
        os.path.join(os.path.dirname(__file__), "data", filename),
        os.path.join(os.getcwd(), "data", filename),
        os.path.join(os.getcwd(), filename)
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Config] Error loading {filename}: {e}")
    return default_payload

titledata_static = load_data_file("titledata.json", {"Results": []})
titledata_map = {entry["key"]: entry["data"] for entry in titledata_static.get("Results", [])}

progtree_data = load_data_file("progression-tree.json", {"Results": []})

STAFF = [
    {"userId": "EA1F059A3FC8F29F", "username": "gorilla7516", "role": 2}
]

BAD_WORDS = [
    "nigger", "nigga", "faggot", "fag", "kike", "spic", "chink", "gook", "raghead",
    "sandnigger", "beaner", "wetback", "coon", "jigaboo", "darkie", "cunt", "twat",
    "whore", "slut", "bitch", "piss", "shit", "fuck", "asshole", "dickhead",
    "cock", "dick", "pussy", "penis", "vagina", "ballsack", "bastard",
    "motherfucker", "motherfuck", "niglet", "tranny", "retard", "mongoloid", "@everyone", "slop", "diddy", "skid"
]

# ─── DATABASE MANAGEMENT ─────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mothershipplayers (
        userid TEXT PRIMARY KEY,
        mothershipid TEXT,
        platform TEXT,
        token TEXT,
        expirationtime INTEGER,
        lastlogin TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mothershiptitledata (
        datakey TEXT PRIMARY KEY,
        datavalue TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mothershipuserdata (
        mothershipid TEXT,
        keyname TEXT,
        datavalue TEXT,
        updatedat TEXT,
        PRIMARY KEY(mothershipid, keyname)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mothershipinventory (
        mothershipid TEXT PRIMARY KEY,
        inventoryjson TEXT,
        updatedat TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS progressionnodes (
        mothershipid TEXT,
        treeid TEXT,
        nodeid TEXT,
        PRIMARY KEY(mothershipid, treeid, nodeid)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ghostgames (
        mothershipid TEXT,
        ghost_game_id TEXT,
        event_timestamp TEXT,
        final_cores_balance INTEGER,
        total_cores_collected_by_player INTEGER,
        total_cores_collected_by_group INTEGER,
        total_cores_spent_by_player INTEGER,
        total_cores_spent_by_group INTEGER,
        gates_unlocked INTEGER,
        died INTEGER,
        items_purchased TEXT,
        shift_cut_data TEXT,
        play_duration INTEGER,
        started_late TEXT,
        time_started TEXT,
        reason TEXT,
        max_number_in_game INTEGER,
        end_number_in_game INTEGER,
        items_picked_up TEXT,
        revives INTEGER,
        num_shifts_played INTEGER,
        game_version TEXT,
        game_environment TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shifts (
        shiftid TEXT PRIMARY KEY,
        mothershipid TEXT,
        completed INTEGER
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dear_lemmings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mothershipid TEXT,
        message_text TEXT,
        display_name TEXT,
        createdat TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS players (
        playfabid TEXT PRIMARY KEY,
        oculusid TEXT,
        sessionticket TEXT,
        entitytoken TEXT,
        entityid TEXT,
        displayname TEXT,
        lastlogin TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oculus_profiles (
        userid TEXT PRIMARY KEY,
        username TEXT
    )""")
    
    conn.commit()
    conn.close()

init_db()

@app.before_request
def before_request():
    g.db = get_db()

@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

# ─── SYSTEM UTILITIES & EXTERNAL WRAPPERS ────────────────────────────────────
def log_file(name, data):
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.utcnow().isoformat() + "Z"
        line = f"[{timestamp}] {data}\n"
        with open(os.path.join(LOG_DIR, name), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[Logger] Failed writing to {name}: {e}")

def sanitize_str(val, max_len=64):
    if not isinstance(val, str):
        return ""
    val = val.strip()
    return val[:max_len]

# Active tracking manager helper
def active_players_seen(mothership_id):
    active_player_sessions.add(mothership_id)

# Discord Webhook & Message Despatchers
def discord_send_webhook(channel_key, embed):
    hook_url = os.environ.get(f"DISCORD_WEBHOOK_{channel_key.upper()}") or os.environ.get("DISCORD_WEBHOOK_DEFAULT")
    if not hook_url:
        print(f"[Discord Webhook Mock - {channel_key}]: {json.dumps(embed)}")
        return
    try:
        requests.post(hook_url, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        print(f"[Discord Webhook Error]: {e}")

def discord_send_channel_message(channel_id, content=None, embed=None):
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        print(f"[Discord Bot Mock - {channel_id}]: content={content}, embed={embed}")
        fallback_hook = os.environ.get("DISCORD_WEBHOOK_DEFAULT")
        if fallback_hook:
            payload = {}
            if content: payload["content"] = content
            if embed: payload["embeds"] = [embed]
            try:
                requests.post(fallback_hook, json=payload, timeout=5)
            except: pass
        return
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }
    payload = {}
    if content: payload["content"] = content
    if embed: payload["embeds"] = [embed]
    try:
        requests.post(url, json=payload, headers=headers, timeout=5)
    except Exception as e:
        print(f"[Discord Bot API Error]: {e}")

# Ghost game tracking discord publisher helper
def discord_send_ghost_game_end(mothership_id, reason, balance, collected, gates, died, revives, play_min):
    embed = {
        "color": 3066993,
        "description": (
            f"## 👻 Ghost Game Completed\n"
            f"**↓ Session Details ↓**\n"
            f"```[Mothership ID] : {mothership_id}\n"
            f"[End Reason]    : {reason}\n"
            f"[Duration (m)]  : {play_min}\n"
            f"[Final Balance] : {balance}\n"
            f"[Cores Gained]  : {collected}\n"
            f"[Gates Open]    : {gates}\n"
            f"[Deaths]        : {died}\n"
            f"[Revives Given] : {revives}\n```"
        )
    }
    discord_send_webhook("misc", embed)

# ─── SECURE TOKEN ISSUANCE & DATABASE INSERTS ────────────────────────────────
def issue_token(player_id, user_id, platform):
    now = int(time.time())
    exp = now + 7200
    
    payload = {
        "sub": player_id,
        "did": MOTHERSHIP_DEPLOYMENT_ID,
        "env": MOTHERSHIP_ENV_ID,
        "externalService": platform,
        "externalServiceId": user_id,
        "tid": MOTHERSHIP_TITLE_ID,
        "tags": None,
        "orgScopedExternalServiceId": user_id,
        "nbf": now,
        "exp": exp,
        "iat": now,
    }
    
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token, exp * 1000

def ensure_mothership_player(userid, platform):
    cursor = g.db.cursor()
    row = cursor.execute("SELECT * FROM mothershipplayers WHERE userid = ?", (userid,)).fetchone()
    if not row:
        mothership_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO mothershipplayers (userid, mothershipid, platform) VALUES (?, ?, ?)",
            (userid, mothership_id, platform)
        )
        g.db.commit()
        row = cursor.execute("SELECT * FROM mothershipplayers WHERE userid = ?", (userid,)).fetchone()
    return dict(row)

def build_auth_response(player, token, exp_ms):
    return {
        "ExternalProviderId": player["userid"],
        "ExternalProviderUsername": "",
        "IsPrimaryId": True,
        "PlayerId": player["mothershipid"],
        "Tags": None,
        "Token": token,
        "ServerTime": int(time.time() * 1000),
        "ExpirationTime": exp_ms,
    }

def ensure_player_entity(playfab_id):
    cursor = g.db.cursor()
    row = cursor.execute("SELECT * FROM players WHERE playfabid = ?", (playfab_id,)).fetchone()
    if not row:
        cursor.execute("INSERT INTO players (playfabid, lastlogin) VALUES (?, datetime('now'))", (playfab_id,))
        g.db.commit()

# ─── MIDDLEWARE SYSTEM (DECORATORS) ──────────────────────────────────────────
def auth_limiter(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr or "127.0.0.1"
        now = time.time()
        
        if ip not in rate_limit_store:
            rate_limit_store[ip] = []
        
        # Keep window clean of timestamps older than 1 minute
        rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < 60]
        
        if len(rate_limit_store[ip]) >= 15:
            return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
        
        rate_limit_store[ip].append(now)
        return f(*args, **kwargs)
    return decorated_function

def require_mothership_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("x-mothership-token")
        if not token:
            return jsonify({"error": "Mothership validation token required"}), 401
        try:
            # Dynamically verify ES256 signature against local public key
            payload = jwt.decode(token, public_key, algorithms=["ES256"])
            g.mothershipid = payload.get("sub")
            g.mothershippayload = payload
        except Exception as e:
            return jsonify({"error": "Signature validation failed", "details": str(e)}), 401
        return f(*args, **kwargs)
    return decorated_function

# ─── SYSTEM API ENDPOINTS ────────────────────────────────────────────────────

# RIFT / PC Authenticators (One-Step Protocol)
@app.route("/v1/client/player/auth/RIFT", methods=["POST"])
@auth_limiter
def rift_authenticate():
    try:
        body = request.get_json(silent=True) or {}
        userid = sanitize_str(body.get("UserId"), 64)
        
        if not userid:
            return jsonify({"error": "Missing UserId"}), 400
            
        player = ensure_mothership_player(userid, "RIFT")
        now_ms = int(time.time() * 1000)
        
        # Check token viability (needs > 30 minutes active lifespan)
        if player.get("token") and player.get("expirationtime", 0) > now_ms + 1800000:
            active_players_seen(player["mothershipid"])
            return jsonify(build_auth_response(player, player["token"], player["expirationtime"])), 201
            
        token, exp = issue_token(player["mothershipid"], userid, "RIFT")
        
        cursor = g.db.cursor()
        cursor.execute(
            "UPDATE mothershipplayers SET token = ?, expirationtime = ?, lastlogin = datetime('now') WHERE userid = ?",
            (token, exp, userid)
        )
        g.db.commit()
        
        active_players_seen(player["mothershipid"])
        return jsonify(build_auth_response(player, token, exp)), 201
    except Exception as err:
        print("[Mothership Auth/Rift] Error:", str(err))
        return jsonify({
            "message": json.dumps({
                "MothershipErrorCode": 10013,
                "ClientMessage": "Client Authentication Failed",
                "TraceId": str(uuid.uuid4())
            }),
            "statusCode": 401
        }), 401

# Quest Authentication Step 1 (Challenge/Nonce Generation)
@app.route("/v2/player/client/auth/begin/QUEST", methods=["POST"])
@auth_limiter
def quest_auth_begin():
    try:
        body = request.get_json(silent=True) or {}
        userid = sanitize_str(body.get("UserId"), 64)
        
        if not userid:
            return jsonify({"error": "Missing UserId"}), 400
            
        nonce_bytes = os.urandom(64)
        nonce = base64.urlsafe_b64encode(nonce_bytes).decode("utf-8").replace("=", "")
        
        now_ms = int(time.time() * 1000)
        pending_nonces[userid] = {"nonce": nonce, "created": now_ms}
        
        log_file("auth-begin.log", json.dumps({"nonce": nonce, "userId": userid}))
        
        # Clear entries older than 5 minutes
        cutoff = now_ms - 300000
        for uid in list(pending_nonces.keys()):
            if pending_nonces[uid]["created"] < cutoff:
                pending_nonces.pop(uid, None)
                
        resp = {"AttestationNonce": nonce}
        log_file("auth-begin-resp.log", json.dumps(resp))
        return jsonify(resp), 201
    except Exception as err:
        print("[Mothership Auth/Begin] Error:", str(err))
        return jsonify({"error": "Internal server error"}), 500

# Quest Authentication Step 2 (Validation of Platform Integrity Certificate)
@app.route("/v2/player/client/auth/complete/QUEST", methods=["POST"])
@auth_limiter
def quest_auth_complete():
    success_code = 201
    status_code = 401
    try:
        body = request.get_json(silent=True) or {}
        userid = sanitize_str(body.get("UserId"), 64)
        attestation_token = body.get("AttestationToken")
        pending = pending_nonces.get(userid)
        
        log_file("auth-complete.log", json.dumps({
            "userId": userid, 
            "hasToken": bool(attestation_token), 
            "hasNonce": bool(pending)
        }))
        
        if not userid or not attestation_token or not pending:
            log_file("auth-complete-resp.log", "FAIL: missing payload fields")
            return jsonify({
                "message": json.dumps({
                    "MothershipErrorCode": 10013,
                    "ClientMessage": "Client Authentication Failed",
                    "TraceId": str(uuid.uuid4())
                }),
                "statusCode": status_code
            }), status_code
            
        if META_ACCESS_TOKEN:
            verify_url = f"https://graph.oculus.com/platform_integrity/verify?token={requests.utils.quote(attestation_token)}&access_token={requests.utils.quote(META_ACCESS_TOKEN)}"
            result = requests.get(verify_url, timeout=10)
            
            if result.status_code != 200:
                raise Exception(f"Meta integrity system returned non-200 status: {result.status_code}")
                
            parsed = result.json()
            entry_list = parsed.get("data", [])
            entry = entry_list[0] if entry_list else None
            
            if not entry or entry.get("message") != "success" or not entry.get("claims"):
                raise Exception("Invalid cryptographic attestation proof claims")
                
            claims_padded = entry.get("claims", "")
            missing_padding = len(claims_padded) % 4
            if missing_padding:
                claims_padded += '=' * (4 - missing_padding)
                
            claims_json = base64.urlsafe_b64decode(claims_padded.encode('utf-8')).decode('utf-8')
            claims = json.loads(claims_json)
            
            token_nonce = claims.get("request_details", {}).get("nonce")
            if token_nonce != pending["nonce"]:
                raise Exception("Integrity Challenge Nonce verification failure")
                
            app_integrity = claims.get("app_state", {}).get("app_integrity_state")
            log_file("auth-complete-resp.log", f"app_integrity={app_integrity}")
            
            # Sideloaded build counter-measurements
            if app_integrity == "NotRecognized":
                print(f"[Quest Auth] Blocked sideload validation attempt on user={userid}")
                pending_nonces.pop(userid, None)
                discord_send_channel_message("1517537648414031962", None, {
                    "color": 15158332,
                    "description": (
                        "## 🚫 Sideloaded App Blocked\n"
                        "**↓ Details ↓**\n"
                        f"```[User ID] : {userid}\n"
                        "[Platform] : QUEST\n"
                        "[Reason]   : App integrity check failed (NotRecognized - sideloaded)\n```"
                    ),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
                return jsonify({
                    "message": json.dumps({
                        "MothershipErrorCode": 10013,
                        "ClientMessage": "Client Authentication Failed",
                        "TraceId": str(uuid.uuid4())
                    }),
                    "statusCode": status_code
                }), status_code
                
            if not app_integrity or app_integrity == "NotEvaluated":
                print(f"[Quest Auth] Warning: App integrity output status: {app_integrity or 'missing'} on user={userid}")
                
        pending_nonces.pop(userid, None)
        player = ensure_mothership_player(userid, "QUEST")
        now_ms = int(time.time() * 1000)
        
        if player.get("token") and player.get("expirationtime", 0) > now_ms + 1800000:
            active_players_seen(player["mothershipid"])
            print("[Quest Auth/Complete] Returning active cached token")
            return jsonify(build_auth_response(player, player["token"], player["expirationtime"])), success_code
            
        token, exp = issue_token(player["mothershipid"], userid, "QUEST")
        
        cursor = g.db.cursor()
        cursor.execute(
            "UPDATE mothershipplayers SET token = ?, expirationtime = ?, lastlogin = datetime('now') WHERE userid = ?",
            (token, exp, userid)
        )
        g.db.commit()
        
        active_players_seen(player["mothershipid"])
        resp = build_auth_response(player, token, exp)
        log_file("auth-complete-resp.log", f"200 success created: {json.dumps(resp)}")
        return jsonify(resp), success_code
    except Exception as err:
        print("[Mothership Auth/Quest] Complete Error:", str(err))
        log_file("auth-complete-resp.log", f"ERROR: {str(err)}")
        return jsonify({
            "message": json.dumps({
                "MothershipErrorCode": 10013,
                "ClientMessage": "Client Authentication Failed",
                "TraceId": str(uuid.uuid4())
            }),
            "statusCode": status_code
        }), status_code

# Batch Client Analytics Processing Engine
@app.route("/v1/client/analytics/event/batch", methods=["POST"])
def client_analytics_batch():
    # Return immediately to avoid holding system resource loops
    response_data = jsonify({})
    
    body = request.get_json(silent=True) or {}
    
    # Run log parsing in sync scope
    try:
        if not os.path.exists(EVENT_LOG_DIR):
            os.makedirs(EVENT_LOG_DIR, exist_ok=True)
        current_date = datetime.utcnow().strftime("%Y-%m-%d")
        log_path = os.path.join(EVENT_LOG_DIR, f"analytics-events-{current_date}.log")
        
        token = request.headers.get("x-mothership-token")
        raw_events = body.get("Events", [])
        
        log_payload = {
            "time": datetime.utcnow().isoformat() + "Z",
            "token": "present" if token else "missing",
            "events": [
                {
                    "name": e.get("EventName"),
                    "tags": e.get("CustomTags"),
                    "body": e.get("Body", {})
                } for e in raw_events
            ]
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_payload) + "\n")
    except Exception as e:
        print("[Analytics] Log writing exception:", e)
        
    mothershipid = None
    token = request.headers.get("x-mothership-token")
    if token:
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            mothershipid = decoded.get("sub")
        except:
            pass
            
    try:
        events = body.get("Events", [])
        cursor = g.db.cursor()
        for evt in events:
            name = evt.get("EventName")
            evt_body = evt.get("Body", {})
            tags = evt.get("CustomTags", {})
            
            if name == "ghost_game_end" and mothershipid:
                cores_collected = int(evt_body.get("total_cores_collected_by_player", 0))
                cores_spent = int(evt_body.get("total_cores_spent_by_player", 0))
                reason = evt_body.get("reason", "unknown")
                
                cursor.execute("""
                    INSERT INTO ghostgames (
                        mothershipid, ghost_game_id, event_timestamp,
                        final_cores_balance, total_cores_collected_by_player, total_cores_collected_by_group,
                        total_cores_spent_by_player, total_cores_spent_by_group,
                        gates_unlocked, died, items_purchased, shift_cut_data, play_duration,
                        started_late, time_started, reason, max_number_in_game, end_number_in_game,
                        items_picked_up, revives, num_shifts_played, game_version, game_environment
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    mothershipid,
                    evt_body.get("ghost_game_id"),
                    evt_body.get("event_timestamp"),
                    int(evt_body.get("final_cores_balance", 0)),
                    cores_collected,
                    int(evt_body.get("total_cores_collected_by_group", 0)),
                    cores_spent,
                    int(evt_body.get("total_cores_spent_by_group", 0)),
                    int(evt_body.get("gates_unlocked", 0)),
                    int(evt_body.get("died", 0)),
                    json.dumps(evt_body.get("items_purchased", [])),
                    str(evt_body.get("shift_cut_data", "0")),
                    int(evt_body.get("play_duration", 0)),
                    str(evt_body.get("started_late", "False")),
                    str(evt_body.get("time_started", "0")),
                    reason,
                    int(evt_body.get("max_number_in_game", 0)),
                    int(evt_body.get("end_number_in_game", 1)),
                    json.dumps(evt_body.get("items_picked_up", {})),
                    int(evt_body.get("revives", 0)),
                    int(evt_body.get("num_shifts_played", 0)),
                    tags.get("tag1"),
                    tags.get("tag2")
                ))
                
                # Settle pending shift objects
                shifts_to_update = cursor.execute("SELECT shiftid FROM shifts WHERE mothershipid = ? AND completed = 0", (mothershipid,)).fetchall()
                for shift in shifts_to_update:
                    cursor.execute("UPDATE shifts SET completed = 1 WHERE shiftid = ?", (shift["shiftid"],))
                    log_file("resdump.log", json.dumps({"event": "ghost_game_end_completed_shift", "mothershipid": mothershipid, "shiftid": shift["shiftid"]}))
                
                g.db.commit()
                
                play_duration = int(evt_body.get("play_duration", 0))
                play_min = round(play_duration / 10000000 / 60 * 100) / 100
                discord_send_ghost_game_end(
                    mothershipid, reason,
                    int(evt_body.get("final_cores_balance", 0)),
                    cores_collected,
                    int(evt_body.get("gates_unlocked", 0)),
                    int(evt_body.get("died", 0)),
                    int(evt_body.get("revives", 0)),
                    play_min
                )
                
            elif name == "game_mode_played_event" and mothershipid:
                gm = evt_body.get("game_mode", "unknown")
                etype = evt_body.get("EventType", "unknown")
                discord_send_webhook("misc", {
                    "color": 3447003,
                    "description": (
                        "## Game Mode Event\n"
                        "**↓ Details ↓**\n"
                        f"```[Mothership ID] : {mothershipid[:12]}\n"
                        f"[Game Mode]     : {gm}\n"
                        f"[Type]          : {etype}\n```"
                    )
                })
    except Exception as e:
        log_file("resdump.log", f"[analytics-error] {str(e)}")
        
    return response_data, 200       

# Client Game Dynamic Configuration Engine (Title Data Endpoint)

TITLE_DATA_EN = {
    "GorillanalyticsChance": 4320,
    "COCRanked": "-NO RACISM, SEXISM, HOMOPHOBIA, TRANSPHOBIA, OR OTHER BIGOTRY\n-ABSOLUTELY NO CHEATS OR MODS\n-DO NOT HARASS OTHER PLAYERS OR INTENTIONALLY MAKE THEM UNCOMFORTABLE\n-DO NOT TROLL OR GRIEF LOBBIES BY BEING UNCATCHABLE OR BY ESCAPING THE MAP. TRY TO MAKE SURE EVERYONE IS HAVING FUN\n-IF SOMEONE IS BREAKING THIS CODE, PLEASE REPORT THEM\n-PLEASE BE NICE GORILLAS AND MAY THE BEST MONKE WIN",
    "CityEventCountdownTimer": "6/13/2026 6:00:00 PM",
    "ActivationReferenceDate": "6/26/2026 5:00:00 PM",
    "ArenaForestSign": "DISCORD.GG/jpbps8kMak",
    "TOBAlreadyOwnPurchaseBtnTxt": "DISCORD.GG/jpbps8kMak",
    "PrivateCrittersGrabSettings": 7,
    "TOBDefPurchaseBtnDefTxt": "DISCORD.GG/jpbps8kMak",
    "PublicCrittersGrabSettings": 1,
    "TOBAlreadyOwnCompTxt": "DISCORD.GG/jpbps8kMak",
    "AnnouncementData": "{\n    \"ShowAnnouncement\": \"false\",\n    \"AnnouncementID\": \"kID_Prelaunch\",\n    \"AnnouncementTitle\": \"IMPORTANT NEWS\",\n    \"Message\": \"We're working to make Gorilla Tag a better, more age-appropriate experience in our next update. To learn more, please check out our Discord.\"\n  }",
    "SharedBlocksTopMapConfig": "{\n    \"rangeMax\": 4,\n    \"sortMethod\": \"Top\",\n    \"useMapID\": false,\n    \"mapID\": \"\"\n  }",
    "PUNErrorLogging": 0,
    "TOBDefCompTxt": "DISCORD.GG/jpbps8kMak",
    "ArenaRulesSign": "RULES:\n\n+CAN'T RUN WITH THE BALL\n\n+CAN'T GRAB THE BALL WHEN IT'S THE OTHER TEAM'S COLOR\n\n+BALL COLOR CHANGES FOR A FEW SECONDS WHEN DROPPED\n\n+SCORE BY HOLDING THE BALL IN THE OTHER TEAM'S GOAL\n\n\nRESTARTING THE GAME:\n\nDROP THE BALL INTO THE START SLOT, THEN THE OTHER TEAM MUST PRESS START GAME",
    "PromoHutSignText": "time is running out!\nshop the gcon collection\nIn-game rewards!\n\nshopgtag.com",
    "TOBSafeCompTxt": "DISCORD.GG/jpbps8kMak",
    "UseLegacyIAP": False,
    "CreatorFest": "{\"Data\":[{\"TitleDataObjectID\":\"CreatorEvent\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"6/13/2026 6:00:00 PM\",\"EndDateTime\":\"6/15/2026 12:00:00 AM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"CreatorObjects\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"6/13/2026 6:00:00 PM\",\"EndDateTime\":\"6/26/2026 12:00:00 AM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"CreatorObjectsCity\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"6/13/2026 5:00:00 PM\",\"EndDateTime\":\"6/26/2026 12:00:00 AM\"}],\"RelativeDateTimeWindow\":[]}]}",
    "GConVidDrops": "{\"Data\":[{\"TitleDataObjectID\":\"GConVidDrop01\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"6/26/2026 2:00:00 PM\",\"EndDateTime\":\"6/29/2026 3:00:00 PM\"}],\"RelativeDateTimeWindow\":[]}]}",
    "CavernDig": "{\"Data\":[{\"TitleDataObjectID\":\"CavernDig1\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/12/2026 6:00:00 PM\",\"EndDateTime\":\"4/22/2026 6:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"CavernDig2\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/22/2026 6:00:00 PM\",\"EndDateTime\":\"4/29/2026 6:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"CavernDig3\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/25/2026 6:00:00 PM\",\"EndDateTime\":\"4/29/2026 6:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"CavernDig4\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/29/2026 6:00:00 PM\",\"EndDateTime\":\"5/2/3333 6:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"CavernDig5\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"5/2/3333 6:00:00 PM\",\"EndDateTime\":\"5/5/3333 6:00:00 PM\"}],\"RelativeDateTimeWindow\":[]}]}",
    "TimedStoreEvent": "6/15/2026 8:00:00 AM",
    "CityObjectSchedule": "{\"Data\":[{\"TitleDataObjectID\":\"Clock\",\"AbsoluteDateTimeWindow\":[],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"HowManyMonke\",\"AbsoluteDateTimeWindow\":[],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"GiantTV\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/1/2026 12:00:00 AM\",\"EndDateTime\":\"4/5/2026 12:00:00 AM\"}],\"RelativeDateTimeWindow\":[]}]}",
    "AllActiveQuests": "{\"DailyQuests\":[{\"selectCount\":1,\"name\":\"Gameplay\",\"quests\":[{\"disable\":false,\"questID\":11,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY INFECTION\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"INFECTION\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"forest\",\"canyon\",\"beach\",\"mountain\",\"skyJungle\",\"cave\",\"Metropolis\",\"rotating\",\"none\"]},{\"disable\":false,\"questID\":19,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY PAINTBRAWL\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"PAINTBRAWL\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"forest\",\"canyon\",\"beach\",\"mountain\",\"skyJungle\",\"cave\",\"Metropolis\",\"rotating\",\"none\"]},{\"disable\":true,\"questID\":13,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY FREEZE TAG\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"FREEZE TAG\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"forest\",\"canyon\",\"beach\",\"mountain\",\"skyJungle\",\"cave\",\"Metropolis\",\"rotating\",\"none\"]},{\"disable\":false,\"questID\":1,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY GUARDIAN\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"GUARDIAN\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"forest\",\"canyon\",\"beach\",\"mountain\",\"cave\",\"Metropolis\",\"none\"]},{\"disable\":false,\"questID\":4,\"weight\":1,\"category\":\"NONE\",\"questName\":\"TAG PLAYERS\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GameModeTag\",\"requiredOccurenceCount\":2,\"requiredZones\":[\"none\"]}]},{\"selectCount\":1,\"name\":\"Ghost Reactor\",\"quests\":[{\"disable\":false,\"questID\":35,\"weight\":1,\"category\":\"NONE\",\"questName\":\"COLLECT GHOST CORES AS A CREW\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRCollectCore\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":36,\"weight\":1,\"category\":\"NONE\",\"questName\":\"SMASH BREAKABLES IN GHOST REACTOR\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRSmashBreakable\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":37,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PURGE GHOSTS AS A CREW\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRKillEnemy\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":39,\"weight\":1,\"category\":\"NONE\",\"questName\":\"BREAK A GHOST'S ARMOR\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRArmorBreak\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":40,\"weight\":1,\"category\":\"NONE\",\"questName\":\"END A SHIFT WITH MORE PURGES THAN INCIDENTS\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRShiftGoodKD\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]}]},{\"selectCount\":2,\"name\":\"Exploration\",\"quests\":[{\"disable\":false,\"questID\":5,\"weight\":1,\"category\":\"NONE\",\"questName\":\"RIDE THE SHARK\",\"questType\":\"grabObject\",\"questOccurenceFilter\":\"ReefSharkRing\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":9,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY THE PIANO\",\"questType\":\"tapObject\",\"questOccurenceFilter\":\"Piano_Collapsed_Key\",\"requiredOccurenceCount\":10,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":14,\"weight\":1,\"category\":\"NONE\",\"questName\":\"THROW SNOWBALLS\",\"questType\":\"launchedProjectile\",\"questOccurenceFilter\":\"SnowballProjectile\",\"requiredOccurenceCount\":10,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":15,\"weight\":1,\"category\":\"NONE\",\"questName\":\"GO FOR A SWIM\",\"questType\":\"swimDistance\",\"questOccurenceFilter\":\"\",\"requiredOccurenceCount\":200,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":21,\"weight\":1,\"category\":\"NONE\",\"questName\":\"CLIMB THE TALLEST TREE\",\"questType\":\"enterLocation\",\"questOccurenceFilter\":\"TallestTree\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"forest\"]},{\"disable\":false,\"questID\":22,\"weight\":1,\"category\":\"NONE\",\"questName\":\"COMPLETE THE OBSTACLE COURSE\",\"questType\":\"enterLocation\",\"questOccurenceFilter\":\"ObstacleCourse\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":23,\"weight\":1,\"category\":\"NONE\",\"questName\":\"SWIM UNDER A WATERFALL\",\"questType\":\"enterLocation\",\"questOccurenceFilter\":\"UnderWaterfall\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":24,\"weight\":1,\"category\":\"NONE\",\"questName\":\"SNEAK UPSTAIRS IN THE STORE\",\"questType\":\"enterLocation\",\"questOccurenceFilter\":\"SecretStore\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":25,\"weight\":1,\"category\":\"NONE\",\"questName\":\"CLIMB INTO THE CROW'S NEST\",\"questType\":\"enterLocation\",\"questOccurenceFilter\":\"CrowsNest\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":26,\"weight\":1,\"category\":\"NONE\",\"questName\":\"GO FOR A WALK\",\"questType\":\"moveDistance\",\"questOccurenceFilter\":\"\",\"requiredOccurenceCount\":500,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":28,\"weight\":1,\"category\":\"NONE\",\"questName\":\"GET SMALL\",\"questType\":\"misc\",\"questOccurenceFilter\":\"SizeSmall\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":29,\"weight\":1,\"category\":\"NONE\",\"questName\":\"GET BIG\",\"questType\":\"misc\",\"questOccurenceFilter\":\"SizeLarge\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":31,\"weight\":1,\"category\":\"NONE\",\"questName\":\"ADD A CRITTER TO YOUR COLLECTION\",\"questType\":\"critter\",\"questOccurenceFilter\":\"Collect\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":32,\"weight\":1,\"category\":\"NONE\",\"questName\":\"DONATE A CRITTER\",\"questType\":\"critter\",\"questOccurenceFilter\":\"Donate\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]}]},{\"selectCount\":1,\"name\":\"Social\",\"quests\":[{\"disable\":false,\"questID\":2,\"weight\":1,\"category\":\"NONE\",\"questName\":\"HIGH FIVE PLAYERS\",\"questType\":\"triggerHandEffect\",\"questOccurenceFilter\":\"HIGH_FIVE\",\"requiredOccurenceCount\":10,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":3,\"weight\":1,\"category\":\"NONE\",\"questName\":\"FIST BUMP PLAYERS\",\"questType\":\"triggerHandEffect\",\"questOccurenceFilter\":\"FIST_BUMP\",\"requiredOccurenceCount\":10,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":16,\"weight\":1,\"category\":\"NONE\",\"questName\":\"FIND SOMETHING TO EAT\",\"questType\":\"eatObject\",\"questOccurenceFilter\":\"\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":30,\"weight\":1,\"category\":\"NONE\",\"questName\":\"MAKE A FRIENDSHIP BRACELET\",\"questType\":\"misc\",\"questOccurenceFilter\":\"FriendshipGroupJoined\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]}]}],\"WeeklyQuests\":[{\"selectCount\":1,\"name\":\"Gameplay\",\"quests\":[{\"disable\":false,\"questID\":17,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY INFECTION\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"INFECTION\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":20,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY PAINTBRAWL\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"PAINTBRAWL\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":8,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY FREEZE TAG\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"FREEZE TAG\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":10,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PLAY GUARDIAN\",\"questType\":\"gameModeRound\",\"questOccurenceFilter\":\"GUARDIAN\",\"requiredOccurenceCount\":25,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":12,\"weight\":1,\"category\":\"NONE\",\"questName\":\"TAG PLAYERS\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GameModeTag\",\"requiredOccurenceCount\":10,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":41,\"weight\":1,\"category\":\"NONE\",\"questName\":\"PURGE GHOSTS AS A CREW\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRKillEnemy\",\"requiredOccurenceCount\":25,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":42,\"weight\":1,\"category\":\"NONE\",\"questName\":\"SMASH BREAKABLES IN GHOST REACTOR\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRSmashBreakable\",\"requiredOccurenceCount\":25,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":38,\"weight\":1,\"category\":\"NONE\",\"questName\":\"GET A GORILLACORP PROMOTION\",\"questType\":\"misc\",\"questOccurenceFilter\":\"GRPromoted\",\"requiredOccurenceCount\":1,\"requiredZones\":[\"none\"]}]},{\"selectCount\":1,\"name\":\"Exploration and Social\",\"quests\":[{\"disable\":true,\"questID\":33,\"weight\":1,\"category\":\"NONE\",\"questName\":\"COLLECT CRITTERS\",\"questType\":\"critter\",\"questOccurenceFilter\":\"Collect\",\"requiredOccurenceCount\":5,\"requiredZones\":[\"none\"]},{\"disable\":true,\"questID\":34,\"weight\":1,\"category\":\"NONE\",\"questName\":\"DONATE CRITTERS\",\"questType\":\"critter\",\"questOccurenceFilter\":\"Donate\",\"requiredOccurenceCount\":10,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":6,\"weight\":1,\"category\":\"NONE\",\"questName\":\"THROW SNOWBALLS\",\"questType\":\"launchedProjectile\",\"questOccurenceFilter\":\"SnowballProjectile\",\"requiredOccurenceCount\":50,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":7,\"weight\":1,\"category\":\"NONE\",\"questName\":\"GO FOR A LONG SWIM\",\"questType\":\"swimDistance\",\"questOccurenceFilter\":\"\",\"requiredOccurenceCount\":1000,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":18,\"weight\":1,\"category\":\"NONE\",\"questName\":\"EAT FOOD\",\"questType\":\"eatObject\",\"questOccurenceFilter\":\"\",\"requiredOccurenceCount\":25,\"requiredZones\":[\"none\"]},{\"disable\":false,\"questID\":27,\"weight\":1,\"category\":\"NONE\",\"questName\":\"GO FOR A LONG WALK\",\"questType\":\"moveDistance\",\"questOccurenceFilter\":\"\",\"requiredOccurenceCount\":2500,\"requiredZones\":[\"none\"]}]}]}",
    "SharedBlocksStartingMapConfig": "{\"pageNumber\":0,\"pageSize\":50,\"sortMethod\":\"Top\",\"useMapID\":false,\"mapID\":\"\"}",
    "VIMSpecialThanks": "I LOVE ALL OF YOU GUYS!!! - MONTERREY",
    "VODScheduleFeatured": "{\"hourly\":[{\"stream\":{\"name\":\"VMT HIGHLIGHT\",\"hideUpNext\":true,\"id\":\"8fd8d9d3-3ebf-4be3-b4d9-01bad5713907\",\"url\":\"\",\"type\":0,\"duration\":1,\"ch\":5,\"displayTitle\":\"\"},\"minute\":0,\"repeats\":[10,20,30,40,50],\"startDateTime\":\"1/1/2000 12:00:00 AM\",\"endDateTime\":\"1/1/3000 12:00:00 AM\"}]}",
    "CityEventCountdown": "{\"Data\":[{\"TitleDataObjectID\":\"Countdown\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/4/2026 7:00:00 PM\",\"EndDateTime\":\"6/13/2026 6:00:00 PM\"}],\"RelativeDateTimeWindow\":[]}]}",
    "GoTime": "6/02/2026 21:30:00 PM",
    "Hatchery": "{\"Data\":[{\"TitleDataObjectID\":\"EventStart\",\"AbsoluteDateTimeWindow\":[],\"RelativeDateTimeWindow\":[{\"StartDateTime\":{\"DaysPast\":0,\"Hours\":0,\"Minutes\":-1,\"Seconds\":0},\"EndDateTime\":{\"DaysPast\":0,\"Hours\":0,\"Minutes\":5,\"Seconds\":0}}]},{\"TitleDataObjectID\":\"TransportSequencer\",\"AbsoluteDateTimeWindow\":[],\"RelativeDateTimeWindow\":[{\"StartDateTime\":{\"DaysPast\":0,\"Hours\":0,\"Minutes\":0,\"Seconds\":0},\"EndDateTime\":{\"DaysPast\":0,\"Hours\":0,\"Minutes\":10,\"Seconds\":0}}]},{\"TitleDataObjectID\":\"EventEnd\",\"AbsoluteDateTimeWindow\":[],\"RelativeDateTimeWindow\":[{\"StartDateTime\":{\"DaysPast\":0,\"Hours\":0,\"Minutes\":5,\"Seconds\":0},\"EndDateTime\":{\"DaysPast\":3650,\"Hours\":0,\"Minutes\":0,\"Seconds\":0}}]}]}",
    "CreatorHutATMCode": "vmt$d9u9yddiHDm18DQtyvO9R",
    "CreatorStore_Thanks": "I\u2019VE GOT MY SPOT IN THE CREATOR STORE TO PROVE TO YOU GUYS THAT I\u2019M NOT A HILLBILLY!\n\nSEE GUYS THERES NO OVERALLS!\n\nI TOLD YOU, AND I EVEN HAVE A FANCY BANANA, USE CODE VMT!",
    "MOTD": "<color=green>WELCOME TO PLUNGER TAG!!</color>\n<color=red>DONT PLAY ZXE TAG IS VERY BAD DOWNLOAD IT AND YOU'RE BANNED EW EW EW EW EW EW</color>\nTHE LATEST UPDATE111!!111!!!\nDISCORD IS: https://discord.gg/5m9AXSKEwj\n<color=yellow>RATE THE GAME 5 STARS SO WE CAN GET RECOMMENDED!!!</color>\nBOARD OF FAME:\nMONTERREY: FOR EVERYTHING, MAKING ART, MAKING GAME, ETC.\nOGS: BILLY, CHILLZ, GREY, MONTERREY, BADGE, RXPTER",
    "SeasonalStoreBoardSign": "<color=green>PLUNGER TAG!</color>\n<color=blue>discord.gg/jpbps8kMak</color>",
    "EventWarnings": "{\"Data\":[{\"TitleDataObjectID\":\"5min\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/11/2026 5:54:30 PM\",\"EndDateTime\":\"4/11/2026 5:55:20 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"4min\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/11/2026 5:55:30 PM\",\"EndDateTime\":\"4/11/2026 5:56:20 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"3min\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/11/2026 5:56:30 PM\",\"EndDateTime\":\"4/11/2026 5:57:20 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"2min\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/11/2026 5:57:30 PM\",\"EndDateTime\":\"4/11/2026 5:58:20 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"1min\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/11/2026 5:58:30 PM\",\"EndDateTime\":\"4/11/2026 5:59:20 PM\"}],\"RelativeDateTimeWindow\":[]}]}",
    "CreatorCoutureATMSign": "support vmt!",
    "PropHuntProps_BetaJook": "LMAAZ.\nLHABC.\nLMAAI.\nLHAIA.\nLHABR.\nLMABJ.\nLFACR.\nLMAOY.\nLMAGR.\nLMAAJ.\nLMAHX.\nLFADU.\nLBABC.\nLHADV.\nLFABC.\nLMAAN.\nLHAGJ.\nLHACY.\nLHAEU.\nLHAHM.\nLFACB.\nLFACA.\nLHAAE.\nLMAHY.\nLHABK.\nLHAEK.\nLMANV.\nLMADL.\nLHAIB.\nLMABS.\nLMALF.\nLHAAG.\nLHADL.\nLHACU.\nLHAIG.\nLHAHX.\nLHAGA.\nLFACG.\nLHAAK.\nLFABX.\nLMACS.\nLHAAH.\nLHAJC.\nLMALO.\nLMAAK.\nLMAJU.\nLMALH.\nLHACE.\nLMANB.\nLMAEK.\nLFAFH.\nLMAKK.\nLFAAJ.\nLBABB.\nLHAGY.\nLMAAA.\nLMAFG.\nLHAFG.\nLFAAW.\nLHADW.\nLMAEU.\nLHACS.\nLMADX.\nLMALS.\nLHACJ.\nLMAFI.\nLFAFP.\nLFACK.\nLHAEZ.\nLHABY.\nLMABR.\nLHAFB.\nLMALY.\nLHABD.\nLHAGC.\nLMABH.\nLHADM.\nLHABA.\nLFAFB.\nLHAED.\nLFAFY.\nLHADQ.\nLMAFE.\nLFAEL.\nLFAEA.\nLMADW.\nLMAFA.\nLHACA.\nLHAHV.\nLFAEC.\nLMAKD.\nLFAAO.\nLFAAV.\nLHAAA.\nLMAGZ.\nLHABG.\nLMAOL.\nLHAHQ.\nLMAKF.\nLFAFZ.\nLFAFY.\nLFAHA.\nLHAJG.\nLFAHK.\nLHACX.\nLBAAP.\nLFABE.\nLMABC.\nLMAAW.\nLHAAC.",
    "COC": "-NO RACISM, SEXISM, HOMOPHOBIA, TRANSPHOBIA, OR OTHER BIGOTRY\n-NO CHEATS OR MODS\n-DO NOT HARASS OTHER PLAYERS OR INTENTIONALLY MAKE THEM UNCOMFORTABLE\n-DO NOT TROLL OR GRIEF LOBBIES BY BEING UNCATCHABLE OR BY ESCAPING THE MAP. TRY TO MAKE SURE EVERYONE IS HAVING FUN\n-IF SOMEONE IS BREAKING THIS CODE, PLEASE REPORT THEM\n-PLEASE BE NICE GORILLAS AND HAVE A GOOD TIME",
    "PropHuntProps": "LMAAZ.\nLHABC.\nLMAAI.\nLHAIA.\nLHABR.\nLMABJ.\nLFACR.\nLMAOY.\nLMAGR.\nLMAAJ.\nLMAHX.\nLFADU.\nLBABC.\nLHADV.\nLFABC.\nLMAAN.\nLHAGJ.\nLHACY.\nLHAEU.\nLHAHM.\nLFACB.\nLFACA.\nLHAAE.\nLMAHY.\nLHABK.\nLHAEK.\nLMANV.\nLMADL.\nLHAIB.\nLMABS.\nLMALF.\nLHAAG.\nLHADL.\nLHACU.\nLHAIG.\nLHAHX.\nLHAGA.\nLFACG.\nLHAAK.\nLFABX.\nLMACS.\nLHAAH.\nLHAJC.\nLMALO.\nLMAAK.\nLMAJU.\nLMALH.\nLHACE.\nLMANB.\nLMAEK.\nLFAFH.\nLMAKK.\nLFAAJ.\nLBABB.\nLHAGY.\nLMAAA.\nLMAFG.\nLHAFG.\nLFAAW.\nLHADW.\nLMAEU.\nLHACS.\nLMADX.\nLMALS.\nLHACJ.\nLMAFI.\nLFAFP.\nLFACK.\nLHAEZ.\nLHABY.\nLMABR.\nLHAFB.\nLMALY.\nLHABD.\nLHAGC.\nLMABH.\nLHADM.\nLHABA.\nLFAFB.\nLHAED.\nLFAFY.\nLHADQ.\nLMAFE.\nLFAEL.\nLFAEA.\nLMADW.\nLMAFA.\nLHACA.\nLHAHV.\nLFAEC.\nLMAKD.\nLFAAO.\nLFAAV.\nLHAAA.\nLMAGZ.\nLHABG.\nLMAOL.\nLHAHQ.\nLMAKF.\nLFAFZ.\nLFAFY.\nLFAHA.\nLHAJG.\nLFAHK.\nLHACX.\nLBAAP.\nLFABE.\nLMABC.\nLMAAW.\nLHAAC.",
    "MovingDrill": "{\"Data\":[{\"TitleDataObjectID\":\"MovingDrill1\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/7/2026 7:00:00 PM\",\"EndDateTime\":\"3/11/2026 7:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"MovingDrill2\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/11/2026 7:00:00 PM\",\"EndDateTime\":\"3/14/2026 7:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"MovingDrill3\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/14/2026 7:00:00 PM\",\"EndDateTime\":\"3/18/2026 7:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"MovingDrill4\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/18/2026 7:00:00 PM\",\"EndDateTime\":\"3/21/2026 7:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"MovingDrill5\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/21/2026 7:00:00 PM\",\"EndDateTime\":\"3/25/2026 7:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"MovingDrill6\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/25/2026 7:00:00 PM\",\"EndDateTime\":\"4/4/2026 2:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"MovingDrill7\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"4/5/2026 2:00:00 PM\",\"EndDateTime\":\"4/11/2026 6:05:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"ScaffoldBase_Normal\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/25/1999 7:00:00 PM\",\"EndDateTime\":\"3/28/2026 7:00:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"ScaffoldBase_Cutout\",\"AbsoluteDateTimeWindow\":[{\"StartDateTime\":\"3/28/2026 7:00:00 PM\",\"EndDateTime\":\"4/4/3333 7:30:00 PM\"}],\"RelativeDateTimeWindow\":[]},{\"TitleDataObjectID\":\"DoorsCaution_Closed\",\"AbsoluteDateTimeWindow\... (47 KB left)
