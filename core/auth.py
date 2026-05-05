from __future__ import annotations
"""OAuth 2.0 Authorization Code Grant with PKCE for Fitbit API."""

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs

import requests

from config import (
    FITBIT_CLIENT_ID,
    FITBIT_CLIENT_SECRET,
    FITBIT_REDIRECT_URI,
    FITBIT_AUTH_URL,
    FITBIT_TOKEN_URL,
    SCOPES,
    TOKEN_FILE,
)


def _generate_code_verifier() -> str:
    """Generate a cryptographically random code verifier (43-128 chars)."""
    return secrets.token_urlsafe(64)[:128]


def _generate_code_challenge(verifier: str) -> str:
    """SHA-256 hash the verifier, base64url encode without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback authorization code."""

    authorization_code = None

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if "code" in query:
            _CallbackHandler.authorization_code = query["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization successful!</h2>"
                b"<p>You can close this window and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            error = query.get("error", ["unknown"])[0]
            self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())

    def log_message(self, format, *args):
        pass  # Suppress request logging


def _get_redirect_port() -> int:
    """Extract port from the redirect URI."""
    parsed = urlparse(FITBIT_REDIRECT_URI)
    return parsed.port or 8080


def authorize() -> dict:
    """Run the full OAuth 2.0 PKCE flow and return token data."""
    if not FITBIT_CLIENT_ID:
        raise ValueError(
            "FITBIT_CLIENT_ID not set. Copy .env.example to .env and add your credentials."
        )

    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)

    params = {
        "client_id": FITBIT_CLIENT_ID,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": SCOPES,
        "redirect_uri": FITBIT_REDIRECT_URI,
    }

    auth_url = f"{FITBIT_AUTH_URL}?{urlencode(params)}"

    port = _get_redirect_port()
    server = HTTPServer(("localhost", port), _CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print(f"\nOpening browser for Fitbit authorization...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback (up to 120 seconds)
    server_thread.join(timeout=120)
    server.server_close()

    if not _CallbackHandler.authorization_code:
        raise TimeoutError("Authorization timed out. Please try again.")

    # Exchange code for tokens
    token_data = _exchange_code(
        _CallbackHandler.authorization_code, code_verifier
    )
    _CallbackHandler.authorization_code = None

    save_tokens(token_data)
    print("Authorization successful! Tokens saved.")
    return token_data


def _exchange_code(code: str, code_verifier: str) -> dict:
    """Exchange authorization code for access and refresh tokens."""
    data = {
        "client_id": FITBIT_CLIENT_ID,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": FITBIT_REDIRECT_URI,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    # Personal/client apps: include client secret in Basic auth if available
    if FITBIT_CLIENT_SECRET:
        credentials = base64.b64encode(
            f"{FITBIT_CLIENT_ID}:{FITBIT_CLIENT_SECRET}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {credentials}"

    response = requests.post(FITBIT_TOKEN_URL, data=data, headers=headers)
    response.raise_for_status()

    token_data = response.json()
    token_data["obtained_at"] = time.time()
    return token_data


def refresh_tokens(refresh_token: str) -> dict:
    """Use a refresh token to obtain new access and refresh tokens."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": FITBIT_CLIENT_ID,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    if FITBIT_CLIENT_SECRET:
        credentials = base64.b64encode(
            f"{FITBIT_CLIENT_ID}:{FITBIT_CLIENT_SECRET}".encode()
        ).decode()
        headers["Authorization"] = f"Basic {credentials}"

    response = requests.post(FITBIT_TOKEN_URL, data=data, headers=headers)
    response.raise_for_status()

    token_data = response.json()
    token_data["obtained_at"] = time.time()
    save_tokens(token_data)
    return token_data


def save_tokens(token_data: dict):
    """Persist token data to disk."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)


def load_tokens() -> dict | None:
    """Load token data from disk, returning None if not found."""
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def get_valid_token() -> str:
    """Return a valid access token, refreshing if expired."""
    token_data = load_tokens()
    if not token_data:
        raise ValueError(
            "No tokens found. Run 'python main.py auth' first."
        )

    obtained_at = token_data.get("obtained_at", 0)
    expires_in = token_data.get("expires_in", 28800)

    if time.time() > obtained_at + expires_in - 300:  # 5-min buffer
        print("Access token expired, refreshing...")
        token_data = refresh_tokens(token_data["refresh_token"])

    return token_data["access_token"]
