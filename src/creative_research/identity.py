from __future__ import annotations

import hashlib
import re


def clean_account_handle(value: object) -> str:
    """Extract a display handle from a TikTok URL or @handle, preserving case."""
    text = "" if value is None else str(value).strip()
    match = re.search(r"tiktok\.com/@([^/?#]+)", text, flags=re.IGNORECASE)
    if match:
        text = match.group(1)
    return text.lstrip("@").strip("/")


def normalize_account(value: object) -> str:
    """Normalize an account handle for registry matching."""
    text = str(value).strip()
    if text.startswith("@"):
        text = text[1:]
    return text.casefold()


def stable_account_id(account: object) -> str:
    """Return a deterministic account identifier."""
    normalized = normalize_account(account)
    return "ACC-" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12].upper()


def stable_post_id(account: object, post_id: object) -> str:
    """Return the same stable POST id used by the reference workspace."""
    raw = f"{str(account).strip()}\0{str(post_id).strip()}".encode()
    return "POST-" + hashlib.sha1(raw).hexdigest()[:12].upper()
