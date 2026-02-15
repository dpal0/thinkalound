from __future__ import annotations

import uuid

from flask import Flask, jsonify, g, request
from flask_cors import CORS

from app.tasks import TaskQueue
from auth.jwt import decode_jwt
from config import load_config
from db import init_db
from api.auth_routes import register_auth_routes
from api.routes import register_routes


def create_app() -> Flask:
    app = Flask(__name__)
    app_config = load_config()
    CORS(
        app,
        supports_credentials=True,
        origins=app_config.cors_allowed_origins or None,
    )
    app.config["APP_CONFIG"] = app_config
    app.config["TASK_QUEUE"] = TaskQueue(app_config.async_worker_count)
    init_db()
    register_auth_routes(app)
    register_routes(app)

    @app.before_request
    def authenticate_request():
        g.user_id = None
        g.github_login = None
        g.is_instructor = False
        token = request.cookies.get(app_config.auth_cookie_name)
        if token:
            try:
                payload = decode_jwt(token)
                g.user_id = uuid.UUID(str(payload.get("sub")))
                g.github_login = payload.get("login")
                g.is_instructor = bool(payload.get("is_instructor"))
            except Exception:
                g.user_id = None

        if request.method == "OPTIONS":
            return None
        if request.path == "/" or request.path.startswith("/auth/"):
            return None
        if g.user_id is None:
            return jsonify({"error": "Authentication required."}), 401
        return None

    @app.errorhandler(ValueError)
    def handle_value_error(err: ValueError):
        return jsonify({"error": str(err)}), 400

    @app.get("/")
    def hello_world() -> str:
        return "Hello, World!"

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8000, debug=True)
