"""Small persistent HTTP adapter. Domain rules live in domain.py."""
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

class Problem(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status

def require(condition, message, status=422):
    if not condition:
        raise Problem(message, status)

def text(data, key):
    value = data.get(key)
    require(isinstance(value, str) and bool(value.strip()), key + " must be a nonempty string")
    return value.strip()

def integer(data, key, minimum=0):
    value = data.get(key)
    require(type(value) is int and value >= minimum, key + " must be an integer >= " + str(minimum))
    return value

def instant(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(dt.tzinfo is not None and dt.utcoffset() is not None, "timestamp must include timezone")
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise Problem("invalid timestamp")

def utcnow():
    return datetime.now(timezone.utc)

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)")
        self.db.execute("INSERT OR IGNORE INTO state VALUES (1, '{}')")
        self.db.commit()

    def transact(self, fn):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            state = json.loads(self.db.execute("SELECT body FROM state WHERE id=1").fetchone()[0])
            result = fn(state)
            self.db.execute("UPDATE state SET body=? WHERE id=1", (json.dumps(state, allow_nan=False),))
            self.db.commit()
            return result
        except BaseException:
            self.db.rollback()
            raise

    def close(self):
        self.db.close()

def serve(dispatch, port=8080):
    store = Store(os.environ.get("DATABASE_PATH", "data.sqlite3"))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.handle_request()
        def do_POST(self):
            self.handle_request()
        def handle_request(self):
            try:
                path = urlsplit(self.path).path.rstrip("/") or "/"
                if self.command == "GET" and path == "/health":
                    self.reply(200, {"ok": True})
                    return
                token = os.environ.get("API_TOKEN")
                if token:
                    import hmac
                    require(hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token), "unauthorized", 401)
                payload = {}
                if self.command == "POST":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        require(0 < length <= 262144, "body must be 1..262144 bytes", 413)
                        payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    except (ValueError, UnicodeDecodeError):
                        raise Problem("invalid JSON", 400)
                    require(isinstance(payload, dict), "JSON object required", 400)
                result = store.transact(lambda state: dispatch(state, self.command, path, payload, utcnow()))
                self.reply(200, result)
            except Problem as exc:
                self.reply(exc.status, {"error": str(exc)})
            except Exception:
                self.reply(500, {"error": "internal error"})
        def reply(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = HTTPServer((os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", port))), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        store.close()
