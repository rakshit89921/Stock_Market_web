from flask import (
    Flask, jsonify, request, send_from_directory, Response,
    session, g
)
from flask_cors import CORS
import os, requests, time, sqlite3, pathlib
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# === Config / constants ===
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

BASE_DIR = pathlib.Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

app = Flask(__name__, static_folder="../public", static_url_path="")
# Allow cookies (sessions) through CORS for your same-origin static frontend
CORS(app, supports_credentials=True)

# Secret key for sessions (set in .env in production!)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",  # set True on HTTPS
)

ALPHA_BASE = "https://www.alphavantage.co/query"

# === Tiny in-memory cache for market APIs ===
_cache = {}
def cache_get(k):
    v = _cache.get(k)
    if not v:
        return None
    data, ts, ttl = v
    if time.time() - ts > ttl:
        return None
    return data

def cache_set(k, data, ttl=50):
    _cache[k] = (data, time.time(), ttl)

def alpha(params, ttl=50):
    if not ALPHAVANTAGE_KEY:
        return jsonify({"error": "ALPHAVANTAGE_KEY missing"}), 500
    key = "alpha:" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    cached = cache_get(key)
    if cached is not None:
        return jsonify(cached)
    params = {**params, "apikey": ALPHAVANTAGE_KEY}
    r = requests.get(ALPHA_BASE, params=params, timeout=30)
    try:
        j = r.json()
    except Exception:
        return Response(r.text, status=r.status_code, mimetype="text/plain")
    cache_set(key, j, ttl)
    return jsonify(j), r.status_code

# === SQLite helpers (users table) ===
def get_db():
    if not hasattr(g, "_db"):
        g._db = sqlite3.connect(DB_PATH)
        g._db.row_factory = sqlite3.Row
    return g._db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()

# Ensure DB is ready at startup
with app.app_context():
    init_db()

# === Public pages ===
@app.get("/")
def root():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/login")
def login_page():
    # Place your login page at: public/login.html
    return send_from_directory(app.static_folder, "login.html")

@app.get("/<path:path>")
def static_proxy(path):
    # Serve all other static assets/pages from /public
    return send_from_directory(app.static_folder, path)

# === Market data APIs ===
@app.get("/api/quote")
def quote():
    symbol = request.args.get("symbol", "RELIANCE.BSE")
    return alpha({"function": "GLOBAL_QUOTE", "symbol": symbol})

@app.get("/api/intraday")
def intraday():
    symbol = request.args.get("symbol", "RELIANCE.BSE")
    interval = request.args.get("interval", "5min")
    return alpha({"function": "TIME_SERIES_INTRADAY", "symbol": symbol, "interval": interval, "outputsize": "compact"})

@app.get("/api/search")
def search():
    q = request.args.get("q", "TCS")
    return alpha({"function": "SYMBOL_SEARCH", "keywords": q})

@app.get("/api/insight")
def insight():
    symbol = request.args.get("symbol", "RELIANCE.BSE")
    if not GROQ_API_KEY:
        return jsonify({"summary": "AI insight unavailable (GROQ_API_KEY not set)."})
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a concise market explainer. Keep responses under 80 words. No financial advice."},
            {"role": "user", "content": f"Give a short, neutral summary for {symbol}. Mention near-term trend risks and catalysts (no numbers)."},
        ],
        "temperature": 0.3,
        "max_tokens": 120
    }
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30)
    try:
        j = r.json()
        txt = j["choices"][0]["message"]["content"].strip()
    except Exception:
        txt = "Insight temporarily unavailable."
    return jsonify({"summary": txt})

# === Auth APIs (session-based) ===
def _json_error(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

@app.post("/api/auth/signup")
def auth_signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return _json_error("Email and password are required.")
    if len(password) < 6:
        return _json_error("Password must be at least 6 characters.")

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users(email, password_hash) VALUES (?, ?)",
            (email, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return _json_error("Email already registered.", 409)

    # Auto-login after signup
    user_id = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    session["uid"] = int(user_id)
    session["email"] = email
    return jsonify({"ok": True, "user": {"email": email}})

@app.post("/api/auth/login")
def auth_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return _json_error("Email and password are required.")

    db = get_db()
    row = db.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return _json_error("Invalid credentials.", 401)

    session["uid"] = int(row["id"])
    session["email"] = email
    return jsonify({"ok": True, "user": {"email": email}})

@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})

@app.get("/api/auth/me")
def auth_me():
    uid = session.get("uid")
    if not uid:
        return _json_error("Not authenticated.", 401)
    return jsonify({"ok": True, "user": {"id": uid, "email": session.get("email")}})

# === Optional: simple auth-required example route ===
@app.get("/api/secure/ping")
def secure_ping():
    if not session.get("uid"):
        return _json_error("Not authenticated.", 401)
    return jsonify({"ok": True, "message": "pong (secure)"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
