from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "instance" / "cctv.db"

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


# Initialise on import as well as direct execution, so both `py run.py` and
# `flask --app run run` create the users table before registration is used.
init_db()


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
    return jsonify(message="Login successful.", user={"name": user["name"], "username": user["username"]})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out successfully.")


@app.get("/api/session")
def current_session():
    if "user_id" not in session:
        return jsonify(authenticated=False), 401
    return jsonify(authenticated=True, user={"name": session["name"]})


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(BASE_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
