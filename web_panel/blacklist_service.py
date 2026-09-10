"""内置黑名单系统。

这是 Web 面板内置能力，不作为可删除插件存在。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .paths import PANEL_DATA_DIR

BLACKLIST_FILE = PANEL_DATA_DIR / "blacklist.json"


def _ensure_file() -> None:
    PANEL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not BLACKLIST_FILE.exists():
        BLACKLIST_FILE.write_text("[]", encoding="utf-8")


def _load() -> list[dict]:
    _ensure_file()
    try:
        data = json.loads(BLACKLIST_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    _ensure_file()
    BLACKLIST_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> float:
    return time.time()


def _normalize_name(name: str) -> str:
    return str(name or "").strip()


def _is_expired(item: dict, now: float | None = None) -> bool:
    expires_at = item.get("expires_at")
    return bool(expires_at and float(expires_at) <= (now or _now()))


def cleanup_expired() -> int:
    now = _now()
    items = _load()
    kept = [i for i in items if not _is_expired(i, now)]
    removed = len(items) - len(kept)
    if removed:
        _save(kept)
    return removed


def list_entries(include_expired: bool = False) -> dict:
    cleanup_expired()
    now = _now()
    items = _load()
    out = []
    for item in items:
        expired = _is_expired(item, now)
        if expired and not include_expired:
            continue
        copied = dict(item)
        copied["expired"] = expired
        copied["remaining_seconds"] = None if not copied.get("expires_at") else max(0, int(float(copied["expires_at"]) - now))
        out.append(copied)
    out.sort(key=lambda i: i.get("created_at", 0), reverse=True)
    return {"ok": True, "data": out}


def find_active(name: str, xuid: str = "") -> dict | None:
    cleanup_expired()
    normalized = _normalize_name(name).lower()
    x = (xuid or "").strip().lower()
    if not normalized and not x:
        return None
    for item in _load():
        name_hit = normalized and _normalize_name(item.get("name")).lower() == normalized
        xuid_hit = x and str(item.get("xuid", "") or "").lower() == x
        if (name_hit or xuid_hit) and not _is_expired(item):
            return item
    return None


def add_entry(name: str, reason: str = "", duration_minutes: int | float | str = 0, operator: str = "Web 面板", xuid: str = "") -> dict:
    name = _normalize_name(name)
    if not name:
        return {"ok": False, "error": "玩家名不能为空"}
    reason = str(reason or "").strip() or "未填写原因"
    x = (xuid or "").strip().lower()
    try:
        duration = float(duration_minutes or 0)
    except Exception:
        duration = 0
    now = _now()
    expires_at = None if duration <= 0 else now + duration * 60
    # 同名或同 XUID 去重（改名后按 XUID 命中，避免重复拉黑）
    items = [
        i for i in _load()
        if not (_normalize_name(i.get("name")).lower() == name.lower() or (x and str(i.get("xuid", "") or "").lower() == x))
    ]
    entry = {
        "id": uuid.uuid4().hex,
        "name": name,
        "xuid": x or None,
        "reason": reason[:120],
        "created_at": now,
        "expires_at": expires_at,
        "operator": str(operator or "Web 面板")[:32],
    }
    items.append(entry)
    _save(items)
    return {"ok": True, "data": entry, "message": "已加入黑名单"}


def remove_entry(entry_id: str = "", name: str = "") -> dict:
    items = _load()
    before = len(items)
    if entry_id:
        items = [i for i in items if i.get("id") != entry_id]
    elif name:
        normalized = _normalize_name(name).lower()
        items = [i for i in items if _normalize_name(i.get("name")).lower() != normalized]
    else:
        return {"ok": False, "error": "缺少删除目标"}
    _save(items)
    return {"ok": True, "removed": before - len(items), "message": "已移出黑名单"}
