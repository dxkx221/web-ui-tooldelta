"""插件配置表单服务。

目标：把插件配置文件转成“小白能填的配置项”，不直接暴露整份文件。
"""
from __future__ import annotations

import configparser
import json
from pathlib import Path
from typing import Any

from .paths import PLUGIN_CFG_DIR, safe_join

SUPPORTED_EXTS = {".json", ".ini", ".cfg"}


def _rel(path: Path) -> str:
    return str(path.relative_to(PLUGIN_CFG_DIR)).replace("\\", "/")


def _field_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, tuple)):
        return "list"
    return "text"


def _flatten_json(value: Any, prefix: str = "") -> list[dict]:
    fields: list[dict] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            fields.extend(_flatten_json(child, path))
    elif isinstance(value, list):
        if all(not isinstance(i, (dict, list)) for i in value):
            fields.append({
                "path": prefix,
                "label": prefix.split(".")[-1] if prefix else "值",
                "type": "list",
                "value": json.dumps(value, ensure_ascii=False),
                "hint": "列表，每行或 JSON 数组均可",
            })
    else:
        fields.append({
            "path": prefix,
            "label": prefix.split(".")[-1] if prefix else "值",
            "type": _field_type(value),
            "value": value,
            "hint": "",
        })
    return fields


def _load_json(path: Path) -> tuple[dict, list[dict]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"value": data}, _flatten_json({"value": data})
    return data, _flatten_json(data)


def _load_ini(path: Path) -> tuple[configparser.ConfigParser, list[dict]]:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    fields: list[dict] = []
    for section in parser.sections():
        for key, value in parser.items(section):
            fields.append({
                "path": f"{section}.{key}",
                "label": key,
                "group": section,
                "type": "text",
                "value": value,
                "hint": "",
            })
    return parser, fields


def _plugin_name_for(path: Path) -> str:
    rel = path.relative_to(PLUGIN_CFG_DIR)
    if len(rel.parts) > 1:
        return rel.parts[0]
    return path.stem


def list_configs() -> dict:
    PLUGIN_CFG_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(PLUGIN_CFG_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTS:
            continue
        try:
            _, fields = _load_file(path)
        except Exception as e:
            items.append({
                "path": _rel(path),
                "plugin": _plugin_name_for(path),
                "name": path.name,
                "field_count": 0,
                "ok": False,
                "error": str(e),
            })
            continue
        items.append({
            "path": _rel(path),
            "plugin": _plugin_name_for(path),
            "name": path.name,
            "field_count": len(fields),
            "ok": True,
        })
    return {"ok": True, "data": items}


def _load_file(path: Path):
    ext = path.suffix.lower()
    if ext == ".json":
        return _load_json(path)
    if ext in {".ini", ".cfg"}:
        return _load_ini(path)
    raise ValueError("暂不支持该配置格式")


def get_config(rel_path: str) -> dict:
    path = safe_join(PLUGIN_CFG_DIR, rel_path)
    if path is None or not path.is_file():
        return {"ok": False, "error": "配置文件不存在"}
    if path.suffix.lower() not in SUPPORTED_EXTS:
        return {"ok": False, "error": "暂不支持该配置格式"}
    try:
        _, fields = _load_file(path)
        return {
            "ok": True,
            "data": {
                "path": _rel(path),
                "plugin": _plugin_name_for(path),
                "name": path.name,
                "fields": fields,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _coerce(value: Any, field_type: str) -> Any:
    if field_type == "bool":
        return str(value).lower() in {"1", "true", "yes", "on", "开启"}
    if field_type == "int":
        return int(value)
    if field_type == "float":
        return float(value)
    if field_type == "list":
        if isinstance(value, list):
            return value
        text = str(value).strip()
        if text.startswith("["):
            return json.loads(text)
        return [line.strip() for line in text.splitlines() if line.strip()]
    return "" if value is None else str(value)


def _set_json_value(data: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = data
    for key in keys[:-1]:
        cur = cur.setdefault(key, {})
    cur[keys[-1]] = value


def save_config(rel_path: str, values: dict) -> dict:
    path = safe_join(PLUGIN_CFG_DIR, rel_path)
    if path is None or not path.is_file():
        return {"ok": False, "error": "配置文件不存在"}
    ext = path.suffix.lower()
    try:
        _, fields = _load_file(path)
        field_map = {f["path"]: f for f in fields}
        if ext == ".json":
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {"value": data}
            for key, raw in (values or {}).items():
                if key in field_map:
                    _set_json_value(data, key, _coerce(raw, field_map[key]["type"]))
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        elif ext in {".ini", ".cfg"}:
            parser, _ = _load_ini(path)
            for key, raw in (values or {}).items():
                if key not in field_map or "." not in key:
                    continue
                section, option = key.split(".", 1)
                if not parser.has_section(section):
                    parser.add_section(section)
                parser.set(section, option, str(raw))
            with path.open("w", encoding="utf-8") as f:
                parser.write(f)
        else:
            return {"ok": False, "error": "暂不支持保存该格式"}
        return {
            "ok": True,
            "message": "插件配置已保存；如果插件正在运行，通常需要重启 ToolDelta 后生效。",
            "needs_restart": True,
            "data": get_config(rel_path).get("data"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
