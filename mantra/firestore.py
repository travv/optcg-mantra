"""Tiny Firestore REST client — query() against opbounty-3623c.

Firestore's typed-value envelope:
  {"stringValue": "OP08-098"}  -> "OP08-098"
  {"doubleValue": 1411.157}    -> 1411.157
  {"integerValue": "5"}        -> 5
  {"booleanValue": true}       -> True
  {"nullValue": None}          -> None
  {"timestampValue": "..."}    -> "..." (ISO string, passed through)
We unwrap on read so callers see plain Python dicts.
"""

import httpx

from auth import FIRESTORE_BASE, FirebaseAuth, _ssl_context


class FirestoreError(Exception):
    pass


def _unwrap(value: dict):
    """Firestore typed-value -> Python value."""
    if not isinstance(value, dict) or not value:
        return value
    (kind, v), = value.items()
    if kind == "stringValue":
        return v
    if kind == "integerValue":
        return int(v)
    if kind == "doubleValue":
        return float(v)
    if kind == "booleanValue":
        return bool(v)
    if kind == "nullValue":
        return None
    if kind == "timestampValue":
        return v
    if kind == "mapValue":
        return {k: _unwrap(x) for k, x in (v.get("fields") or {}).items()}
    if kind == "arrayValue":
        return [_unwrap(x) for x in (v.get("values") or [])]
    if kind == "referenceValue":
        return v
    return v


def _unwrap_doc(doc: dict) -> dict:
    out = {k: _unwrap(v) for k, v in (doc.get("fields") or {}).items()}
    out["_name"] = doc.get("name")
    out["_create_time"] = doc.get("createTime")
    out["_update_time"] = doc.get("updateTime")
    return out


class Firestore:
    def __init__(self, auth: FirebaseAuth | None = None) -> None:
        self._auth = auth or FirebaseAuth()
        self._client = httpx.Client(
            verify=_ssl_context(),
            timeout=60.0,
        )

    def run_query(
        self,
        collection: str,
        where: list[tuple[str, str, object]] | None = None,
        order_by: tuple[str, str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Run a structuredQuery against a top-level collection.

        Args:
            collection: collection id, e.g. "Replays".
            where: list of (field, op, value). op is one of
                EQUAL, NOT_EQUAL, LESS_THAN, LESS_THAN_OR_EQUAL,
                GREATER_THAN, GREATER_THAN_OR_EQUAL, ARRAY_CONTAINS, IN.
                Values are auto-typed: str -> stringValue, int -> integerValue,
                float -> doubleValue, bool -> booleanValue.
            order_by: (field, "ASCENDING"|"DESCENDING").
            limit: maximum docs to return (Firestore caps a single page at 10000).
        """
        filters = []
        for f, op, v in (where or []):
            filters.append({
                "fieldFilter": {
                    "field": {"fieldPath": f},
                    "op": op,
                    "value": _wrap_value(v),
                }
            })
        if len(filters) == 1:
            query_filter = filters[0]
        elif filters:
            query_filter = {
                "compositeFilter": {"op": "AND", "filters": filters}
            }
        else:
            query_filter = None

        structured = {
            "from": [{"collectionId": collection}],
            "limit": limit,
        }
        if query_filter is not None:
            structured["where"] = query_filter
        if order_by is not None:
            field, direction = order_by
            structured["orderBy"] = [{
                "field": {"fieldPath": field},
                "direction": direction,
            }]

        url = f"{FIRESTORE_BASE}/documents:runQuery"
        resp = self._client.post(
            url,
            json={"structuredQuery": structured},
            headers=self._auth.auth_header(),
        )
        if resp.status_code != 200:
            raise FirestoreError(
                f"runQuery failed ({resp.status_code}): {resp.text[:500]}"
            )
        out = []
        for entry in resp.json():
            doc = entry.get("document")
            if doc:
                out.append(_unwrap_doc(doc))
        return out

    def list_collection(
        self,
        collection: str,
        page_size: int = 50,
        page_token: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """Plain GET /documents/<collection> with pagination (no filters)."""
        url = f"{FIRESTORE_BASE}/documents/{collection}"
        params = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        resp = self._client.get(url, params=params, headers=self._auth.auth_header())
        if resp.status_code != 200:
            raise FirestoreError(
                f"list_collection failed ({resp.status_code}): {resp.text[:500]}"
            )
        body = resp.json()
        return [_unwrap_doc(d) for d in body.get("documents", [])], body.get("nextPageToken")


def _wrap_value(v) -> dict:
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if v is None:
        return {"nullValue": None}
    return {"stringValue": str(v)}
