"""Card-art asset bootstrap: copy from local caches first, fall back to download."""
import os
import shutil
import ssl
import sys
import urllib.error
import urllib.request

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

CARD_ART_URL = "https://en.onepiece-cardgame.com/images/cardlist/card/{cid}.png"


def ensure_assets(
    card_ids: set[str],
    target_dir: str,
    extra_sources: list[str] | None = None,
) -> tuple[int, int, list[str]]:
    """Ensure `<target_dir>/<cid>.png` exists for every id in `card_ids`.

    Copies from existing caches in `extra_sources` first, falls back to
    download from the official card-list CDN. Returns
    (copied, downloaded, missing_ids).
    """
    target_dir = os.path.expanduser(target_dir)
    os.makedirs(target_dir, exist_ok=True)
    sources = [os.path.expanduser(p) for p in (extra_sources or [])]

    copied = 0
    downloaded = 0
    missing: list[str] = []
    for cid in sorted(card_ids):
        target = os.path.join(target_dir, f"{cid}.png")
        if os.path.exists(target):
            continue
        found_local = None
        for src in sources:
            cand = os.path.join(src, f"{cid}.png")
            if os.path.exists(cand):
                found_local = cand
                break
        if found_local:
            shutil.copyfile(found_local, target)
            copied += 1
            continue
        url = CARD_ART_URL.format(cid=cid)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as r:
                data = r.read()
            with open(target, "wb") as f:
                f.write(data)
            downloaded += 1
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            missing.append(cid)
            print(f"  WARN: could not fetch {cid}: {e}", file=sys.stderr)
    return copied, downloaded, missing


def available_assets_in(target_dir: str) -> set[str]:
    target_dir = os.path.expanduser(target_dir)
    if not os.path.isdir(target_dir):
        return set()
    return {
        os.path.splitext(f)[0]
        for f in os.listdir(target_dir)
        if f.endswith(".png")
    }
