from __future__ import annotations

import secrets
import os

from flask import Flask, Response, jsonify, redirect, request

from auth.jwt import decode_jwt, issue_jwt
from auth.oauth import build_github_authorize_url, exchange_code_for_token, fetch_github_user, fetch_primary_email
from config import AppConfig
from db import session_scope
from db.storage import consume_oauth_state, create_oauth_state, upsert_oauth_token, upsert_user


def register_auth_routes(app: Flask) -> None:
    @app.get("/auth/github")
    def auth_github() -> Response:
        state = secrets.token_urlsafe(24)
        with session_scope() as session:
            create_oauth_state(session, state)
        url = build_github_authorize_url(state)
        return redirect(url)

    @app.get("/auth/github/callback")
    def auth_github_callback() -> Response:
        code = request.args.get("code")
        state = request.args.get("state")
        if not code or not state:
            return jsonify({"error": "Missing code or state."}), 400

        with session_scope() as session:
            if not consume_oauth_state(session, state):
                return jsonify({"error": "Invalid OAuth state."}), 400

        token = exchange_code_for_token(code)
        user_data = fetch_github_user(token)
        primary_email = fetch_primary_email(token)

        github_user_id = str(user_data.get("id", ""))
        github_login = str(user_data.get("login", ""))
        name = user_data.get("name")
        email = primary_email or user_data.get("email")
        if not github_user_id or not github_login:
            return jsonify({"error": "GitHub user data missing."}), 400

        config: AppConfig = app.config["APP_CONFIG"]
        is_instructor = github_login in config.instructors

        with session_scope() as session:
            user = upsert_user(session, github_user_id, github_login, name, email)
            upsert_oauth_token(session, user.id, token)

        jwt_token = issue_jwt(
            user_id=str(user.id),
            github_login=github_login,
            is_instructor=is_instructor,
            exp_minutes=config.auth_jwt_exp_minutes,
        )

        response = redirect(_get_redirect_url(config))
        response.set_cookie(
            config.auth_cookie_name,
            jwt_token,
            httponly=True,
            secure=config.auth_cookie_secure,
            samesite=config.auth_cookie_samesite,
            max_age=config.auth_jwt_exp_minutes * 60,
            path="/",
        )
        return response

    @app.get("/auth/me")
    def auth_me() -> tuple[Response, int]:
        config: AppConfig = app.config["APP_CONFIG"]
        token = request.cookies.get(config.auth_cookie_name)
        if not token:
            return jsonify({"authenticated": False}), 200
        try:
            payload = decode_jwt(token)
        except Exception:
            return jsonify({"authenticated": False}), 200
        login = payload.get("login")
        return (
            jsonify(
                {
                    "authenticated": True,
                    "github_login": login,
                    "is_instructor": bool(login in config.instructors),
                }
            ),
            200,
        )

    @app.post("/auth/logout")
    def auth_logout() -> tuple[Response, int]:
        config: AppConfig = app.config["APP_CONFIG"]
        response = jsonify({"ok": True})
        response.set_cookie(
            config.auth_cookie_name,
            "",
            httponly=True,
            secure=config.auth_cookie_secure,
            samesite=config.auth_cookie_samesite,
            max_age=0,
            path="/",
        )
        return response, 200


def _get_redirect_url(config: AppConfig) -> str:
    env = os.getenv("AUTH_REDIRECT_URL", "").strip()
    if env:
        return env.rstrip("/")
    return config.auth_redirect_url.rstrip("/")
