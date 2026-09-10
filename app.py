import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, session, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash


# --------------------------------------------------
# APP SETUP
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mindora.db")

app = Flask(__name__, static_folder="public", static_url_path="")

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-in-render"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if os.environ.get("RENDER"):
    app.config["SESSION_COOKIE_SECURE"] = True

CORS(app, supports_credentials=True)


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def now():
    return datetime.now(timezone.utc).isoformat()


def initialize_database():
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            text TEXT NOT NULL,
            mood_name TEXT NOT NULL,
            mood_emoji TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS likes (
            post_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, username),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            message_type TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # Add sample posts ONLY if database is empty
    count = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    if count == 0:
        sample_posts = [
            (
                "Anonymous_27",
                "user",
                "Sometimes I feel like no one understands what I'm going through, but writing it down here makes me feel a little lighter.",
                "Loved",
                "❤️",
                now()
            ),
            (
                "Admin_Sarah",
                "admin",
                "Welcome everyone to Mindora! Remember to treat each other with kindness. We are so glad you are here.",
                "Happy",
                "😄",
                now()
            ),
            (
                "Anonymous_45",
                "user",
                "Grateful for the little things today. Let's all take care of ourselves.",
                "Good",
                "😊",
                now()
            )
        ]

        db.executemany("""
            INSERT INTO posts
            (username, role, text, mood_name, mood_emoji, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, sample_posts)

    db.commit()
    db.close()


initialize_database()


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def current_username():
    return session.get("username")


def current_role():
    return session.get("role", "user")


def staff_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if current_role() not in ("admin", "host", "mod"):
            return jsonify({
                "success": False,
                "message": "Staff access required."
            }), 403

        return function(*args, **kwargs)

    return wrapper


def post_to_json(db, post):
    likes = db.execute(
        "SELECT COUNT(*) FROM likes WHERE post_id = ?",
        (post["id"],)
    ).fetchone()[0]

    username = current_username()

    liked = False

    if username:
        liked = db.execute("""
            SELECT 1
            FROM likes
            WHERE post_id = ? AND username = ?
        """, (post["id"], username)).fetchone() is not None

    return {
        "id": post["id"],
        "user": post["username"],
        "role": post["role"],
        "time": "Just now",
        "text": post["text"],
        "likes": likes,
        "liked": liked,
        "mood": {
            "name": post["mood_name"],
            "emoji": post["mood_emoji"]
        }
    }


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/api/health")
def health():
    return jsonify({
        "success": True,
        "message": "Mindora Python backend is running."
    })


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

@app.post("/api/auth/signup")
def signup():
    data = request.get_json() or {}

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if len(username) < 3 or len(username) > 30:
        return jsonify({
            "success": False,
            "message": "Username must be 3-30 characters."
        }), 400

    if len(password) < 6:
        return jsonify({
            "success": False,
            "message": "Password must be at least 6 characters."
        }), 400

    db = get_db()

    existing = db.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if existing:
        db.close()
        return jsonify({
            "success": False,
            "message": "Username already exists."
        }), 409

    password_hash = generate_password_hash(password)

    db.execute("""
        INSERT INTO users
        (username, password_hash, role, created_at)
        VALUES (?, ?, 'user', ?)
    """, (username, password_hash, now()))

    db.commit()
    db.close()

    session["username"] = username
    session["role"] = "user"

    return jsonify({
        "success": True,
        "username": username,
        "role": "user"
    })


@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    db = get_db()

    user = db.execute("""
        SELECT username, password_hash, role
        FROM users
        WHERE username = ?
    """, (username,)).fetchone()

    db.close()

    if not user or not check_password_hash(
        user["password_hash"],
        password
    ):
        return jsonify({
            "success": False,
            "message": "Invalid username or password."
        }), 401

    session["username"] = user["username"]
    session["role"] = user["role"]

    return jsonify({
        "success": True,
        "username": user["username"],
        "role": user["role"]
    })


@app.post("/api/auth/staff-login")
def staff_login():
    data = request.get_json() or {}

    username = str(data.get("username", "")).strip()
    access_key = str(data.get("accessKey", ""))

    correct_key = os.environ.get("STAFF_ACCESS_KEY")

    if not correct_key:
        return jsonify({
            "success": False,
            "message": "Staff access is not configured yet."
        }), 503

    staff_roles = {
        os.environ.get("ADMIN_USERNAME", "Admin_Sarah"): "admin",
        os.environ.get("HOST_USERNAME", "Host_Name"): "host",
        os.environ.get("MOD_USERNAME", "Mod_Name"): "mod"
    }

    role = staff_roles.get(username)

    if not role or access_key != correct_key:
        return jsonify({
            "success": False,
            "message": "Invalid staff credentials."
        }), 401

    session["username"] = username
    session["role"] = role

    return jsonify({
        "success": True,
        "username": username,
        "role": role
    })


@app.get("/api/auth/me")
def auth_me():
    username = current_username()

    if not username:
        return jsonify({
            "loggedIn": False
        })

    return jsonify({
        "loggedIn": True,
        "username": username,
        "role": current_role()
    })


@app.post("/api/auth/logout")
def logout():
    session.clear()

    return jsonify({
        "success": True
    })


# --------------------------------------------------
# POSTS
# --------------------------------------------------

@app.get("/api/posts")
def get_posts():
    db = get_db()

    rows = db.execute("""
        SELECT *
        FROM posts
        ORDER BY id DESC
    """).fetchall()

    result = [post_to_json(db, post) for post in rows]

    db.close()

    return jsonify(result)


@app.post("/api/posts")
def create_post():
    data = request.get_json() or {}

    text = str(data.get("text", "")).strip()

    if not text:
        return jsonify({
            "success": False,
            "message": "Post cannot be empty."
        }), 400

    if len(text) > 2000:
        return jsonify({
            "success": False,
            "message": "Post is too long."
        }), 400

    username = current_username()

    if not username:
        username = "Anonymous_" + str(
            int(datetime.now().timestamp())
        )[-5:]

    role = current_role()

    mood = data.get("mood") or {}

    mood_name = str(mood.get("name", "Good"))
    mood_emoji = str(mood.get("emoji", "😊"))

    db = get_db()

    cursor = db.execute("""
        INSERT INTO posts
        (username, role, text, mood_name, mood_emoji, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        username,
        role,
        text,
        mood_name,
        mood_emoji,
        now()
    ))

    post_id = cursor.lastrowid

    db.commit()

    post = db.execute(
        "SELECT * FROM posts WHERE id = ?",
        (post_id,)
    ).fetchone()

    result = post_to_json(db, post)

    db.close()

    return jsonify(result), 201


@app.delete("/api/posts/<int:post_id>")
@staff_required
def delete_post(post_id):
    db = get_db()

    post = db.execute(
        "SELECT id FROM posts WHERE id = ?",
        (post_id,)
    ).fetchone()

    if not post:
        db.close()
        return jsonify({
            "success": False,
            "message": "Post not found."
        }), 404

    db.execute(
        "DELETE FROM posts WHERE id = ?",
        (post_id,)
    )

    db.commit()
    db.close()

    return jsonify({
        "success": True
    })


@app.put("/api/posts/<int:post_id>/like")
def like_post(post_id):
    username = current_username()

    if not username:
        return jsonify({
            "success": False,
            "message": "Please log in to like posts."
        }), 401

    data = request.get_json() or {}
    increment = bool(data.get("increment"))

    db = get_db()

    post = db.execute(
        "SELECT * FROM posts WHERE id = ?",
        (post_id,)
    ).fetchone()

    if not post:
        db.close()
        return jsonify({
            "success": False,
            "message": "Post not found."
        }), 404

    already_liked = db.execute("""
        SELECT 1
        FROM likes
        WHERE post_id = ? AND username = ?
    """, (post_id, username)).fetchone()

    if increment and not already_liked:
        db.execute("""
            INSERT INTO likes
            (post_id, username, created_at)
            VALUES (?, ?, ?)
        """, (post_id, username, now()))

    elif not increment and already_liked:
        db.execute("""
            DELETE FROM likes
            WHERE post_id = ? AND username = ?
        """, (post_id, username))

    db.commit()

    updated_post = db.execute(
        "SELECT * FROM posts WHERE id = ?",
        (post_id,)
    ).fetchone()

    result = post_to_json(db, updated_post)

    db.close()

    return jsonify(result)


# --------------------------------------------------
# CONTACT / STAFF INBOX
# --------------------------------------------------

@app.post("/api/contact")
def create_contact():
    data = request.get_json() or {}

    text = str(data.get("text", "")).strip()
    message_type = str(
        data.get("type", "General")
    ).strip()

    if not text:
        return jsonify({
            "success": False,
            "message": "Message cannot be empty."
        }), 400

    username = current_username() or "Anonymous"

    db = get_db()

    cursor = db.execute("""
        INSERT INTO contact_messages
        (sender, message_type, text, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        username,
        message_type,
        text,
        now()
    ))

    message_id = cursor.lastrowid

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "id": message_id
    }), 201


@app.get("/api/contact")
@staff_required
def get_contact():
    db = get_db()

    messages = db.execute("""
        SELECT
            id,
            sender,
            message_type,
            text,
            created_at
        FROM contact_messages
        ORDER BY id DESC
    """).fetchall()

    result = []

    for message in messages:
        result.append({
            "id": message["id"],
            "sender": message["sender"],
            "type": message["message_type"],
            "text": message["text"]
        })

    db.close()

    return jsonify(result)


# --------------------------------------------------
# FRONTEND
# --------------------------------------------------

@app.route("/")
def home():
    return send_from_directory(
        app.static_folder,
        "index.html"
    )


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )