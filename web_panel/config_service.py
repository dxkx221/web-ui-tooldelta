"""启动配置服务：读/写 ToolDelta基本配置.json 与 fbtoken 文件，供 Web 表单使用。

关键设计（不碰框架源码）：
- `ConfigLoader.load_tooldelta_cfg_and_get_launcher()` 的交互点全部可被「预置配置文件」绕过：
    * launchMode 非 0          -> 跳过启动器选择（不 input）
    * 「全局GitHub镜像」非空    -> 跳过镜像测速配置（不 input）
    * 原版：服务器号/密码/验证服务器地址非空 -> 不 input；fbtoken 需写 fbtoken 文件（否则 if_token 会 input）
- 因此 Web 端只需把表单写入配置文件（+ 可选 fbtoken 文件），即可让框架无 TTY 启动。
"""
import json
import os
from pathlib import Path

from .paths import CFG_FILE, FBTOKEN_FILE

# 启动器元数据（与 config_loader.LAUNCHERS_SHOWN 顺序一致，1 基）
LAUNCHERS = [
    {
        "index": 1,
        "name": "NeOmega 接入点",
        "desc": "NeOmega 模式，租赁服适应性强",
        "key": "NeOmega接入点启动模式",
        "builtin": False,
        "fields": [
            {"k": "服务器号", "label": "服务器号/山头码", "type": "text"},
            {"k": "密码", "label": "服务器密码", "type": "password"},
            {"k": "验证服务器地址(更换时记得更改fbtoken)", "label": "验证服务器地址", "type": "text"},
        ],
    },
    {
        "index": 2,
        "name": "NeOmega 远程接入点",
        "desc": "连接已启动的 NeOmega 接入点",
        "key": "NeOmega远程接入点模式",
        "builtin": False,
        "fields": [
            {"k": "远程连接地址", "label": "远程连接地址", "type": "text"},
        ],
    },
    {
        "index": 3,
        "name": "NeOmega 并行模式",
        "desc": "同时运行 NeOmega 和 ToolDelta",
        "key": "NeOmega并行ToolDelta启动模式",
        "builtin": False,
        "fields": [
            {"k": "服务器号", "label": "服务器号/山头码", "type": "text"},
            {"k": "密码", "label": "服务器密码", "type": "password"},
            {"k": "验证服务器地址(更换时记得更改fbtoken)", "label": "验证服务器地址", "type": "text"},
        ],
    },
    {
        "index": 4,
        "name": "Eulogist",
        "desc": "赞颂者和 ToolDelta 并行使用（无需配置）",
        "key": None,
        "builtin": False,
        "fields": [],
    },
    {
        "index": 5,
        "name": "FateArk",
        "desc": "FateArk 接入点",
        "key": "FateArk接入点启动模式",
        "builtin": False,
        "fields": [
            {"k": "服务器号", "label": "服务器号/山头码", "type": "text"},
            {"k": "密码", "label": "服务器密码", "type": "password"},
            {"k": "验证服务器地址(更换时记得更改fbtoken)", "label": "验证服务器地址", "type": "text"},
        ],
    },
    {
        "index": 6,
        "name": "FateArk 远程",
        "desc": "连接远程 FateArk 接入点",
        "key": "FateArk远程接入点启动模式",
        "builtin": False,
        "fields": [
            {"k": "服务器号", "label": "服务器号/山头码", "type": "text"},
            {"k": "密码", "label": "服务器密码", "type": "password"},
            {"k": "验证服务器地址(更换时记得更改fbtoken)", "label": "验证服务器地址", "type": "text"},
            {"k": "远程连接端口", "label": "远程连接端口（默认 tcp://127.0.0.1:24020）", "type": "text"},
        ],
    },
    {
        "index": 7,
        "name": "NEMCTanGame",
        "desc": "网易本地联机（房间号）",
        "key": "NEMCTanGame接入点启动模式",
        "builtin": False,
        "fields": [
            {"k": "房间号", "label": "房间号", "type": "text"},
            {"k": "密码", "label": "房间密码", "type": "password"},
            {"k": "验证服务器地址(更换时记得更改fbtoken)", "label": "验证服务器地址", "type": "text"},
        ],
    },
]


# 启动时若这些字段为空，框架会在无 TTY 的后台线程里触发 input()/getpass() 卡死。
# 索引 → 必填字段（非空才允许无交互启动）。
# 依据：config_loader._load_original_access_point_data 里，服务器号/密码/验证服务器地址为空均会 input。
REQUIRED_FIELDS = {
    1: ["服务器号", "密码", "验证服务器地址(更换时记得更改fbtoken)"],
    3: ["服务器号", "密码", "验证服务器地址(更换时记得更改fbtoken)"],
    5: ["服务器号", "密码", "验证服务器地址(更换时记得更改fbtoken)"],
    6: ["服务器号", "密码", "验证服务器地址(更换时记得更改fbtoken)"],
    7: ["房间号", "密码", "验证服务器地址(更换时记得更改fbtoken)"],
}
# 这些启动器走 _load_original_access_point_data，需要 fbtoken 文件（否则 if_token 会 input）
REQUIRES_FBTOKEN = {1, 3, 5, 6, 7}


def _load_cfg_raw() -> dict:
    """读取配置（容错，缺失/损坏返回空 dict）。"""
    try:
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cfg(cfg: dict) -> None:
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


def _load_fbtoken() -> str:
    try:
        with open(FBTOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _save_fbtoken(token: str) -> None:
    if token:
        with open(FBTOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(token.replace("\n", ""))
    else:
        try:
            os.remove(FBTOKEN_FILE)
        except OSError:
            pass


def schema() -> list[dict]:
    return LAUNCHERS


def get_config() -> dict:
    """返回当前配置，供前端表单回填。"""
    cfg = _load_cfg_raw()
    launch_mode = cfg.get("启动器启动模式(请不要手动更改此项, 改为0可重置)", 0)
    try:
        launch_mode = int(launch_mode)
    except (ValueError, TypeError):
        launch_mode = 0

    # 找到当前启动器对应的配置段
    current_section = {}
    current_launcher = None
    if 1 <= launch_mode <= len(LAUNCHERS):
        meta = LAUNCHERS[launch_mode - 1]
        current_launcher = meta
        if meta["key"]:
            current_section = cfg.get(meta["key"], {})

    fbtoken = _load_fbtoken()
    missing = _missing_required(launch_mode, current_section, fbtoken)
    return {
        "launch_mode": launch_mode,
        "record_log": cfg.get("是否记录日志", True),
        "github_mirror": cfg.get("全局GitHub镜像", ""),
        "plugin_market": cfg.get("插件市场源", ""),
        "current_launcher": current_launcher["name"] if current_launcher else None,
        "current_section": current_section,
        "fbtoken": fbtoken,
        "fbtoken_set": bool(fbtoken),
        "missing_required": missing,
    }


def _missing_required(launch_mode: int, section: dict, fbtoken: str) -> list[str]:
    """返回当前启动模式缺失的必填项（为空即会触发 input() 卡死）。"""
    missing = []
    for k in REQUIRED_FIELDS.get(launch_mode, []):
        if not str(section.get(k, "") or "").strip():
            missing.append(k)
    if launch_mode in REQUIRES_FBTOKEN and not fbtoken:
        missing.append("fbtoken")
    return missing


def startup_check() -> dict:
    """启动前的配置完整性检查，供 /api/start 拦截。

    返回 {"ok": bool, "error": str|None}。ok=False 时禁止启动，避免框架在
    无 TTY 后台线程里因配置缺失触发交互（虽已被 _BlockingStdin 阻焊成阻塞，
    但会静默卡住，不如在启动前明确拦截并引导用户补全）。
    """
    cfg = _load_cfg_raw()
    launch_mode = cfg.get("启动器启动模式(请不要手动更改此项, 改为0可重置)", 0)
    try:
        launch_mode = int(launch_mode)
    except (ValueError, TypeError):
        launch_mode = 0

    if launch_mode == 0:
        return {"ok": False, "error": "尚未选择启动器，请先到「启动配置」页选择并保存"}
    if launch_mode not in range(1, len(LAUNCHERS) + 1):
        return {"ok": False, "error": "启动器序号不合法，请重新选择"}

    meta = LAUNCHERS[launch_mode - 1]
    section = cfg.get(meta["key"], {}) if meta["key"] else {}
    fbtoken = _load_fbtoken()
    missing = _missing_required(launch_mode, section, fbtoken)
    if missing:
        return {"ok": False, "error": "启动配置缺少必填项：" + "、".join(missing) + "，请补全后再启动"}
    return {"ok": True, "error": None}


def save_config(payload: dict) -> dict:
    """保存配置。payload: {launch_mode, record_log, github_mirror, plugin_market, section, fbtoken}"""
    cfg = _load_cfg_raw()

    launch_mode = int(payload.get("launch_mode", 0) or 0)
    if launch_mode not in range(0, len(LAUNCHERS) + 1):
        return {"ok": False, "error": "启动器序号不合法"}

    # Web 后台线程下 launchMode=0 会触发交互选择（input()）卡死，因此必须选具体启动器
    if launch_mode == 0:
        return {"ok": False, "error": "Web 模式下必须选择具体启动器（不能选交互选择），否则后台启动会卡死"}

    # 收集本次要写入的启动器配置段
    seg = {}
    section = payload.get("section") or {}
    if isinstance(section, dict) and 1 <= launch_mode <= len(LAUNCHERS):
        meta = LAUNCHERS[launch_mode - 1]
        if meta["key"]:
            for f in meta["fields"]:
                seg[f["k"]] = str(section.get(f["k"], "") or "").strip()

    fbtoken = str(payload.get("fbtoken", "") or "").strip()

    # 启动前校验：必填项为空会在无 TTY 后台线程触发 input()/getpass() 卡死
    missing = _missing_required(launch_mode, seg, fbtoken)
    if missing:
        return {"ok": False, "error": "以下必填项为空会导致后台启动卡死，请补全后再保存：" + "、".join(missing)}

    cfg["启动器启动模式(请不要手动更改此项, 改为0可重置)"] = launch_mode
    cfg["是否记录日志"] = bool(payload.get("record_log", True))
    # 镜像留空会导致框架首次启动时交互测速（无 TTY 卡死），故给默认官方镜像
    cfg["全局GitHub镜像"] = str(payload.get("github_mirror", "") or "").strip() or "https://github.tooldelta.top"
    cfg["插件市场源"] = str(payload.get("plugin_market", "") or "").strip()

    if seg and 1 <= launch_mode <= len(LAUNCHERS):
        meta = LAUNCHERS[launch_mode - 1]
        if meta["key"]:
            cfg[meta["key"]] = seg

    _save_cfg(cfg)
    _save_fbtoken(fbtoken)

    return {"ok": True, "data": get_config()}
