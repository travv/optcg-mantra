"""Firebase auth for the OPBounty client (project opbounty-3623c).

The OPBounty desktop app (Godot 4) embeds these credentials in its bundle and
signs in every user as the same shared service account so it can read/write
shared Firestore collections under client-only rules. We use the same path:
POST signInWithPassword -> get a 1-hour ID token -> send as Bearer.

The credentials are not secret — they sit in plain text in the .pck file the
app ships to every user. This module embeds them directly; no on-disk
credential file is needed.
"""

import ssl
import time

import certifi
import httpx

API_KEY = "AIzaSyC9qxZxJZbt2NJkjSyU9b3KJUfRHVFPuVs"
PROJECT_ID = "opbounty-3623c"
STORAGE_BUCKET = "opbounty-3623c.firebasestorage.app"

CLIENT_EMAIL = "opbountyclient@opbounty.com"
CLIENT_PASSWORD = "ClientUser"

IDENTITY_BASE = "https://identitytoolkit.googleapis.com/v1"
FIRESTORE_BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)"
STORAGE_BASE = f"https://firebasestorage.googleapis.com/v0/b/{STORAGE_BUCKET}"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

EXPIRY_SKEW_SECONDS = 300  # refresh 5 minutes before Firebase ID tokens expire


class AuthError(Exception):
    """Raised when Firebase auth fails."""


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


class FirebaseAuth:
    """Holds a cached Firebase ID token, refreshing on demand."""

    def __init__(self) -> None:
        self._id_token: str | None = None
        self._expires_at: float = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            verify=_ssl_context(),
            timeout=30.0,
        )

    def _signin(self) -> str:
        resp = self._client.post(
            f"{IDENTITY_BASE}/accounts:signInWithPassword",
            params={"key": API_KEY},
            json={
                "email": CLIENT_EMAIL,
                "password": CLIENT_PASSWORD,
                "returnSecureToken": True,
            },
        )
        if resp.status_code != 200:
            raise AuthError(
                f"Firebase signInWithPassword failed ({resp.status_code}): "
                f"{resp.text[:300]}"
            )
        body = resp.json()
        token = body.get("idToken")
        ttl = int(body.get("expiresIn", 3600))
        if not token:
            raise AuthError(f"signInWithPassword had no idToken: {body!r}")
        self._id_token = token
        self._expires_at = time.time() + ttl - EXPIRY_SKEW_SECONDS
        return token

    def id_token(self) -> str:
        if self._id_token and time.time() < self._expires_at:
            return self._id_token
        return self._signin()

    def auth_header(self) -> dict:
        return {"Authorization": f"Bearer {self.id_token()}"}

    def selftest(self) -> dict:
        token = self._signin()
        return {
            "signin": "ok",
            "id_token_prefix": token[:14] + "...",
            "expires_in_s": int(self._expires_at + EXPIRY_SKEW_SECONDS - time.time()),
            "project_id": PROJECT_ID,
        }
