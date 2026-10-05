from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from functools import wraps

import cv2
from flask import Flask, Response, abort, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from detection import CameraDetector


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "instance" / "cctv.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

app = Flask(__name__, static_folder=None)
# Set SECRET_KEY in the environment before deployment. This fallback is only for local development.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-local-development-key")


def get_db() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS cameras (
                camera_id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_name TEXT NOT NULL,
                camera_status TEXT NOT NULL DEFAULT 'Online'
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL,
                incident_type TEXT NOT NULL,
                detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                screenshot_path TEXT,
                status TEXT NOT NULL DEFAULT 'New',
                FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                activity TEXT NOT NULL,
                date_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        db.execute(
            "INSERT OR IGNORE INTO cameras (camera_id, camera_name, camera_status) VALUES (1, 'Laptop Webcam', 'Online')"
        )


# Initialise on import as well as direct execution, so both `py run.py` and
# `flask --app run run` create the users table before registration is used.
init_db()


def save_incident(incident_type: str, frame) -> int:
    """Persist a detector event and its annotated frame in SQLite."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now()
    filename = f"incident_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    output_path = UPLOAD_DIR / filename
    if not cv2.imwrite(str(output_path), frame):
        raise RuntimeError("Screenshot could not be written.")
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO incidents (camera_id, incident_type, detected_at, screenshot_path) VALUES (?, ?, ?, ?)",
            (1, incident_type, timestamp.isoformat(sep=" ", timespec="seconds"), f"/uploads/{filename}"),
        )
        db.execute("INSERT INTO system_logs (activity) VALUES (?)", (incident_type,))
    return cursor.lastrowid


detector = CameraDetector(save_incident)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(message="Please log in first."), 401
        return view(*args, **kwargs)
    return wrapped


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    if not name or not username or not password:
        return jsonify(message="Name, username, and password are required."), 400
    if len(username) < 3:
        return jsonify(message="Username must contain at least 3 characters."), 400
    if len(password) < 6:
        return jsonify(message="Password must contain at least 6 characters."), 400

    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (name, username, password_hash) VALUES (?, ?, ?)",
                (name, username, generate_password_hash(password)),
            )
    except sqlite3.IntegrityError:
        return jsonify(message="That username is already registered."), 409

    return jsonify(message="Registration successful. Please log in."), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    with get_db() as db:
        user = db.execute(
            "SELECT user_id, name, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(message="Invalid username or password. Register first if you do not have an account."), 401

    session.clear()
    session["user_id"] = user["user_id"]
    session["name"] = user["name"]
    with get_db() as db:
        db.execute("INSERT INTO system_logs (user_id, activity) VALUES (?, ?)", (user["user_id"], "Login"))
    return jsonify(message="Login successful.", user={"name": user["name"], "username": user["username"]})


@app.post("/api/logout")
def logout():
    if "user_id" in session:
        with get_db() as db:
            db.execute("INSERT INTO system_logs (user_id, activity) VALUES (?, ?)", (session["user_id"], "Logout"))
    session.clear()
    return jsonify(message="Logged out successfully.")


@app.get("/api/session")
def current_session():
    if "user_id" not in session:
        return jsonify(authenticated=False), 401
    return jsonify(authenticated=True, user={"name": session["name"]})


@app.get("/api/dashboard")
@login_required
def dashboard_data():
    with get_db() as db:
        camera_online = db.execute("SELECT COUNT(*) FROM cameras WHERE camera_status = 'Online'").fetchone()[0]
        total_incidents = db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
        today_incidents = db.execute("SELECT COUNT(*) FROM incidents WHERE date(detected_at, 'localtime') = date('now', 'localtime')").fetchone()[0]
        total_logs = db.execute("SELECT COUNT(*) FROM system_logs").fetchone()[0]
        recent = db.execute(
            """
            SELECT i.incident_id, i.incident_type, i.detected_at, c.camera_name, i.status
            FROM incidents AS i
            JOIN cameras AS c ON c.camera_id = i.camera_id
            ORDER BY i.detected_at DESC, i.incident_id DESC
            LIMIT 5
            """
        ).fetchall()

    return jsonify(
        stats={
            "camera_online": camera_online,
            "total_incidents": total_incidents,
            "today_incidents": today_incidents,
            "total_logs": total_logs,
        },
        recent=[dict(row) for row in recent],
    )


@app.get("/api/detection-status")
@login_required
def detection_status():
    detector.start()
    return jsonify(detector.status())


@app.get("/video_feed")
@login_required
def video_feed():
    return Response(detector.frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/incidents")
@login_required
def incidents_list():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT i.incident_id, i.incident_type, i.detected_at, i.screenshot_path, i.status, c.camera_name
            FROM incidents i JOIN cameras c ON c.camera_id = i.camera_id
            ORDER BY i.detected_at DESC, i.incident_id DESC
            """
        ).fetchall()
    return jsonify(incidents=[dict(row) for row in rows])


@app.get("/api/incidents/<int:incident_id>")
@login_required
def incident_detail(incident_id: int):
    with get_db() as db:
        row = db.execute(
            """
            SELECT i.incident_id, i.incident_type, i.detected_at, i.screenshot_path, i.status, c.camera_name
            FROM incidents i JOIN cameras c ON c.camera_id = i.camera_id
            WHERE i.incident_id = ?
            """,
            (incident_id,),
        ).fetchone()
    if row is None:
        return jsonify(message="Incident not found."), 404
    return jsonify(incident=dict(row))


@app.get("/api/history")
@login_required
def history_list():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT l.log_id, l.activity, l.date_time, COALESCE(u.username, 'System') AS username
            FROM system_logs l LEFT JOIN users u ON u.user_id = l.user_id
            ORDER BY l.date_time DESC, l.log_id DESC LIMIT 100
            """
        ).fetchall()
    return jsonify(logs=[dict(row) for row in rows])


@app.post("/api/incidents")
@login_required
def create_incident():
    """Event endpoint for the future OpenCV/YOLO detection service."""
    data = request.get_json(silent=True) or {}
    incident_type = str(data.get("incident_type", "")).strip()
    if incident_type not in {"Motion Detected", "Person Detected"}:
        return jsonify(message="Incident type must be Motion Detected or Person Detected."), 400

    camera_id = int(data.get("camera_id", 1))
    screenshot_path = str(data.get("screenshot_path", "")).strip() or None
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO incidents (camera_id, incident_type, screenshot_path) VALUES (?, ?, ?)",
            (camera_id, incident_type, screenshot_path),
        )
        db.execute("INSERT INTO system_logs (user_id, activity) VALUES (?, ?)", (session["user_id"], incident_type))
    return jsonify(message="Incident recorded.", incident_id=cursor.lastrowid), 201


@app.get("/uploads/<path:filename>")
@login_required
def incident_upload(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    if filename not in {"app.js", "styles.css", "favicon.ico"}:
        abort(404)
    return send_from_directory(BASE_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
