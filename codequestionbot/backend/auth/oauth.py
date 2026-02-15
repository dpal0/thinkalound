from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import requests


def build_github_authorize_url(state: str) -> str:
    params = {
        "client_id": _get_client_id(),
        "redirect_uri": _get_redirect_uri(),
        "scope": "read:user repo",
        "state": state,
        "allow_signup": "true",
    }
    return f"https://github.com/login/oauth/authorize?{urlencode(params)}"


def exchange_code_for_token(code: str) -> str:
    url = "https://github.com/login/oauth/access_token"
    headers = {"Accept": "application/json"}
    payload = {
        "client_id": _get_client_id(),
        "client_secret": _get_client_secret(),
        "code": code,
        "redirect_uri": _get_redirect_uri(),
    }
    response = requests.post(url, headers=headers, data=payload, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"GitHub token exchange failed: {response.text}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("GitHub token exchange returned no access_token.")
    return str(token)


def fetch_github_user(token: str) -> dict[str, Any]:
    url = "https://api.github.com/user"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"GitHub user fetch failed: {response.text}")
    return response.json()


def fetch_primary_email(token: str) -> str | None:
    url = "https://api.github.com/user/emails"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
        return None
    data = response.json()
    if not isinstance(data, list):
        return None
    for entry in data:
        if entry.get("primary") and entry.get("verified"):
            return entry.get("email")
    return None


def _get_client_id() -> str:
    value = os.getenv("GITHUB_CLIENT_ID")
    if not value:
        raise RuntimeError("GITHUB_CLIENT_ID is not set.")
    return value


def _get_client_secret() -> str:
    value = os.getenv("GITHUB_CLIENT_SECRET")
    if not value:
        raise RuntimeError("GITHUB_CLIENT_SECRET is not set.")
    return value


def _get_redirect_uri() -> str:
    value = os.getenv("GITHUB_REDIRECT_URI")
    if not value:
        raise RuntimeError("GITHUB_REDIRECT_URI is not set.")
    return value
