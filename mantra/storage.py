"""Firebase Storage download for opbounty-3623c.firebasestorage.app.

URL form: https://firebasestorage.googleapis.com/v0/b/<bucket>/o/<urlencoded path>?alt=media
"""

import urllib.parse

import httpx

from auth import STORAGE_BASE, FirebaseAuth, _ssl_context


class StorageError(Exception):
    pass


class Storage:
    def __init__(self, auth: FirebaseAuth | None = None) -> None:
        self._auth = auth or FirebaseAuth()
        self._client = httpx.Client(
            verify=_ssl_context(),
            timeout=60.0,
        )

    def download(self, path: str) -> str:
        """Return the raw text body at the given storage path."""
        encoded = urllib.parse.quote(path, safe="")
        url = f"{STORAGE_BASE}/o/{encoded}"
        resp = self._client.get(
            url,
            params={"alt": "media"},
            headers=self._auth.auth_header(),
        )
        if resp.status_code != 200:
            raise StorageError(
                f"download failed for {path!r} ({resp.status_code}): "
                f"{resp.text[:300]}"
            )
        return resp.text
