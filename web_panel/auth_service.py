"""面板内置登录凭据。

用于 Docker 商用部署时给每个实例生成一套独立的访问账号。
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import string
import time
import urllib.error
import urllib.request
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from .paths import PANEL_DATA_DIR

LEGACY_CREDENTIALS_FILE = PANEL_DATA_DIR / "credentials.json"
CREDENTIALS_FILE = Path(
    os.environ.get("SHENYI_CREDENTIALS_FILE") or LEGACY_CREDENTIALS_FILE
)


def _random_text(length: int, alphabet: str) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _make_username() -> str:
    return "admin_" + _random_text(6, string.ascii_lowercase + string.digits)


def _make_password() -> str:
    alphabet = string.ascii_letters + string.digits
    parts = [_random_text(4, alphabet) for _ in range(3)]
    return "-".join(parts)


def _make_instance_id() -> str:
    node_id = (
        os.environ.get("SHENYI_NODE_ID")
        or os.environ.get("PANEL_NODE_ID")
        or "a"
    )
    node_id = "".join(ch for ch in node_id.lower() if ch.isalnum()) or "a"
    suffix = _random_text(8, string.ascii_lowercase + string.digits)
    return f"{node_id}-{suffix}"


def _public_url(instance_id: str) -> str:
    configured = (
        os.environ.get("SHENYI_PANEL_URL")
        or os.environ.get("PANEL_PUBLIC_URL")
        or os.environ.get("PUBLIC_URL")
    )
    if configured:
        return configured.rstrip("/")
    root_domain = (
        os.environ.get("SHENYI_PANEL_ROOT_DOMAIN")
        or os.environ.get("PANEL_ROOT_DOMAIN")
        or ""
    ).strip().strip(".")
    if not root_domain:
        return ""
    return f"https://{instance_id}.{root_domain}"


def _allocation_key() -> str:
    configured = (
        os.environ.get("SHENYI_ALLOC_KEY")
        or os.environ.get("MCSM_INSTANCE_UUID")
        or os.environ.get("PANEL_ALLOC_KEY")
    )
    if configured:
        return configured.strip()
    hostname = socket.gethostname().strip()
    if hostname:
        return hostname
    return _random_text(16, string.ascii_lowercase + string.digits)


def _allocate_instance(preferred_instance_id: str = "") -> dict:
    url = (
        os.environ.get("SHENYI_ALLOCATOR_URL")
        or os.environ.get("PANEL_ALLOCATOR_URL")
        or ""
    ).strip()
    token = (
        os.environ.get("SHENYI_ALLOCATOR_TOKEN")
        or os.environ.get("PANEL_ALLOCATOR_TOKEN")
        or ""
    ).strip()
    if not url or not token:
        return {}

    payload = {
        "node_id": os.environ.get("SHENYI_NODE_ID") or os.environ.get("PANEL_NODE_ID") or "a",
        "key": _allocation_key(),
        "preferred_instance_id": preferred_instance_id,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {}
    if not result.get("ok") or not isinstance(result.get("data"), dict):
        return {}
    return result["data"]


def _load() -> dict:
    candidates = [CREDENTIALS_FILE]
    if LEGACY_CREDENTIALS_FILE != CREDENTIALS_FILE:
        candidates.append(LEGACY_CREDENTIALS_FILE)
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if path != CREDENTIALS_FILE:
            _save(data)
        return data
    return {}


def _save(data: dict) -> None:
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_credentials() -> dict:
    data = _load()
    if data.get("username") and data.get("password_hash"):
        changed = False
        if (
            not os.environ.get("SHENYI_INSTANCE_ID")
            and not os.environ.get("PANEL_INSTANCE_ID")
            and not data.get("allocation_key")
        ):
            allocation = _allocate_instance(str(data.get("instance_id") or ""))
            if allocation.get("instance_id"):
                data["instance_id"] = allocation["instance_id"]
                data["public_url"] = allocation.get("url")
                data["allocation_key"] = allocation.get("key")
                # 注意：已有本地账密时绝不用分配器返回的账密覆盖 ——
                # 客户可能已持有并保存了原账密，换号会导致老客户登录失败。
                changed = True
        if data.get("instance_id") and not data.get("public_url"):
            data["public_url"] = _public_url(str(data["instance_id"]))
            changed = True
        if changed:
            _save(data)
        return data

    allocation = _allocate_instance()
    username = (
        os.environ.get("SHENYI_PANEL_USERNAME")
        or os.environ.get("PANEL_USERNAME")
        or allocation.get("username")
        or _make_username()
    )
    password = (
        os.environ.get("SHENYI_PANEL_PASSWORD")
        or os.environ.get("PANEL_PASSWORD")
        or allocation.get("password")
        or _make_password()
    )
    instance_id = (
        os.environ.get("SHENYI_INSTANCE_ID")
        or os.environ.get("PANEL_INSTANCE_ID")
        or allocation.get("instance_id")
        or _make_instance_id()
    )
    data = {
        "instance_id": instance_id,
        "public_url": allocation.get("url") or _public_url(instance_id),
        "allocation_key": allocation.get("key"),
        "username": username,
        "password": password,
        "password_hash": generate_password_hash(password),
        "created_at": time.time(),
    }
    _save(data)
    return data


def verify(username: str, password: str) -> bool:
    data = ensure_credentials()
    if str(username or "").strip() != data.get("username"):
        return False
    return check_password_hash(data.get("password_hash", ""), str(password or ""))


def public_credentials() -> dict:
    data = ensure_credentials()
    return {
        "instance_id": data.get("instance_id"),
        "public_url": data.get("public_url"),
        "username": data.get("username"),
        "password": data.get("password"),
        "file": str(CREDENTIALS_FILE),
    }
