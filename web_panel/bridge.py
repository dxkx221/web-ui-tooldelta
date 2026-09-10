"""框架管理器：在后台线程运行 ToolDelta，并向 Web 暴露线程安全的状态/命令/事件接口。

关键设计：
- ToolDelta 单例在 import 时于主线程创建（signal.signal 只能在主线程调用），因此这里在模块级 import。
- bootstrap() 阻塞在 launch_and_wait_closed() 循环，放在独立后台线程执行。
- fmts.print_* 走 logging，由 bus.BusLogHandler 推送（见 bus.py）。
- 结构化聊天：框架 ready 后注册一个 priority=50 的 Text 包监听器（高于 GameCtrl=-1、
  game_utils=1、PluginGroup=0，低于 PlayerInfoMaintainer=100，返回 False 不拦截），
  把聊天解析成结构化事件推送到 bus。
- 无 TTY 防护：启动前把 sys.stdin 替换为「readline() 永久阻塞」的假流。
  框架里 command_readline_proc / reload / 各交互函数的 input() 在无 TTY 后台线程会
  立即抛 EOFError，导致框架被误判为 NORMAL_EXIT 而瞬间退出。替换后它们只会阻塞等待，
  不会崩溃（真实交互靠 Web 表单预填配置绕过，本补丁是最后防线）。
"""
import json
import threading
import sys
import time
import traceback
from typing import Any
from collections import deque

from tooldelta import start_tool_delta, tooldelta
from tooldelta import game_utils
from tooldelta.constants import PacketIDS, SysStatus, TextType
from tooldelta.internal.launch_config import LaunchConfig
from tooldelta.utils import get_playername_and_msg_from_text_packet, mc_translator

from . import blacklist_service
from .bus import bus
from .paths import PANEL_DATA_DIR, PERSIST_DIR


class _BlockingStdin:
    """无 TTY 环境的阻塞 stdin：readline/read 永久等待，不抛 EOFError。

    Python 的 input() 在 sys.stdin 非 tty（isatty() == False）时会直接调用
    readline()。这里让 readline() 阻塞在一个永不 set 的 Event 上，从而：
      - 框架的 input() 调用点（command_readline_proc 等）只阻塞不崩溃
      - 不会触发 EOFError → 不会把 launcher 误判为 NORMAL_EXIT 而退出
    """

    encoding = "utf-8"
    errors = "strict"

    def __init__(self):
        self._never = threading.Event()

    def readline(self, *args, **kwargs):
        self._never.wait()
        return ""

    def read(self, *args, **kwargs):
        self._never.wait()
        return ""

    def isatty(self):
        return False

    def fileno(self):
        return -1

    def flush(self):
        pass


def _patch_stdin_for_web():
    """在 Web 后台线程启动框架前，把 sys.stdin 换成阻塞流。"""
    if not isinstance(sys.stdin, _BlockingStdin):
        sys.stdin = _BlockingStdin()

_STATUS_LABEL = {
    SysStatus.LOADING: "加载中",
    SysStatus.LAUNCHING: "启动中",
    SysStatus.RUNNING: "运行中",
    SysStatus.NORMAL_EXIT: "正常退出",
    SysStatus.FB_LAUNCH_EXC: "启动异常",
    SysStatus.CRASHED_EXIT: "崩溃退出",
    SysStatus.RELOAD: "重载中",
}

ITEM_TRANSLATION_ALIASES = {
    "granite_wall": "tile.cobblestone_wall.granite.name",
    "diorite_wall": "tile.cobblestone_wall.diorite.name",
    "andesite_wall": "tile.cobblestone_wall.andesite.name",
    "mossy_cobblestone_wall": "tile.cobblestone_wall.mossy.name",
    "cobblestone_wall": "tile.cobblestone_wall.normal.name",
    "stone_brick_wall": "tile.cobblestone_wall.stone_brick.name",
    "mossy_stone_brick_wall": "tile.cobblestone_wall.mossy_stone_brick.name",
    "nether_brick_wall": "tile.cobblestone_wall.nether_brick.name",
    "end_stone_brick_wall": "tile.cobblestone_wall.end_brick.name",
    "red_sandstone_wall": "tile.cobblestone_wall.red_sandstone.name",
    "red_nether_brick_wall": "tile.cobblestone_wall.red_nether_brick.name",
    "spruce_planks": "tile.planks.spruce.name",
    "birch_planks": "tile.planks.birch.name",
    "jungle_planks": "tile.planks.jungle.name",
    "acacia_planks": "tile.planks.acacia.name",
    "dark_oak_planks": "tile.planks.big_oak.name",
    "oak_planks": "tile.planks.oak.name",
    "lapis_lazuli": "item.dye.blue.name",
    "soul_sand": "tile.soul_sand.name",
    "wither_skeleton_skull": "item.skull.wither.name",
    "warden_spawn_egg": "item.spawn_egg.entity.warden.name",
    "wither_skeleton_spawn_egg": "item.spawn_egg.entity.wither_skeleton.name",
}


def _mc_translate(key: str) -> str:
    try:
        translated = mc_translator.translate(key)
    except ValueError:
        mc_translator.init_pool()
        translated = mc_translator.translate(key)
    except Exception:
        return ""
    return translated if translated and translated != key else ""


def _item_display_name(item_id: str) -> str:
    key = str(item_id or "").strip().removeprefix("minecraft:")
    key = key.split(":", 1)[0].replace(" ", "_").lower()
    if not key or key == "minecraft" or key.isdigit():
        return ""
    candidates = [
        ITEM_TRANSLATION_ALIASES.get(key, ""),
        f"item.{key}.name",
        f"tile.{key}.name",
        f"item.minecraft.{key}",
        f"block.minecraft.{key}",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        translated = _mc_translate(candidate)
        if translated:
            return translated
    return ""


def _clean_item_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1].strip()
    return text


def _item_custom_name(slot: dict) -> str:
    for key in (
        "customName",
        "custom_name",
        "displayName",
        "display_name",
        "nameTag",
        "name_tag",
        "tagName",
        "Name",
        "name",
    ):
        value = _clean_item_text(slot.get(key))
        if value:
            return value
    for parent_key in ("tag", "nbt", "userData", "extra"):
        parent = slot.get(parent_key)
        if not isinstance(parent, dict):
            continue
        for key in ("CustomName", "customName", "displayName", "Name", "name"):
            value = _clean_item_text(parent.get(key))
            if value:
                return value
    return ""


# 进服审核：玩家被请出时的默认提示语（可在面板自定义，可用 {player} 代指玩家名）
GATE_DEFAULT_MESSAGE = "本服已开启进服审核，请等待管理员批准后再进入"
# 请出前等待秒数：太早踢会导致玩家还在加载、看不到自定义提示语
GATE_KICK_DELAY = 2.5


def _cmd_quote(value: str) -> str:
    text = str(value or "").strip()
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _player_to_dict(p) -> dict:
    return {
        "name": p.name,
        "uuid": p.uuid,
        "unique_id": p.unique_id,
        "xuid": p.xuid,
        "device_id": p.device_id,
        "runtime_id": p.runtime_id,
        "platform_chat_id": p.platform_chat_id,
        "build_platform": p.build_platform,
        "online": p.online,
    }


class FrameManager:
    """ToolDelta 生命周期管理与 Web 桥接门面。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = "idle"  # idle | starting | running | stopped | error
        self._error: str | None = None
        self._thread: threading.Thread | None = None
        self._watcher: threading.Thread | None = None
        self._chat_registered = False
        self._last_ready = False
        self._ops = deque(maxlen=300)
        self._blacklist_kick_until: dict[str, float] = {}
        self._world_rules: dict[str, str] = {}
        self._world_rules_file = PANEL_DATA_DIR / "world_rules.json"
        self._load_world_rules()
        # 玩家名册：XUID/名字/存活玩家，供权限管理等把 XUID 反查成可读玩家名（含离线）
        # 放到持久目录（容器里是 /data 挂载卷），重建容器不丢
        self._player_names_file = PERSIST_DIR / "player_names.json"
        if not self._player_names_file.exists():
            legacy = PANEL_DATA_DIR / "player_names.json"
            try:
                if legacy.exists():
                    self._player_names_file.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        self._player_names: dict[str, dict] = {}
        self._load_player_names()
        # 玩家动态：记录玩家上下线（进出）时间线，持久化到 /data
        self._activity_file = PERSIST_DIR / "player_activity.json"
        self._activity: list[dict] = []
        self._online_prev: dict[str, str] | None = None
        self._presence_started = False
        self._load_activity()
        # 在线人数采样（画曲线）
        self._samples_file = PERSIST_DIR / "online_samples.json"
        self._samples: list[list] = []
        self._last_sample_ts = 0.0
        self._last_sample_count = -1
        self._load_samples()
        # 进服审核 / 白名单（默认关闭）
        self._gate_file = PERSIST_DIR / "join_gate.json"
        self._gate: dict = {"enabled": False, "approved": {}, "pending": [], "rejected": [], "message": ""}
        self._load_gate()
        # 聊天记录（本地关键词检索，不接 AI）
        self._chatlog_file = PERSIST_DIR / "chatlog.jsonl"
        self._chatlog: deque = deque(maxlen=8000)
        self._load_chatlog()

    # ---------- 玩家名册（持久化 xuid -> name，离线也能反查） ----------

    def _load_player_names(self) -> None:
        try:
            if self._player_names_file.exists():
                data = json.loads(self._player_names_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in list(data.items()):
                        if not isinstance(v, dict):
                            continue
                        # 兼容旧格式：只有 name/uuid/seen_at，补 names 历史列表
                        if not isinstance(v.get("names"), list):
                            v["names"] = [v.get("name")] if v.get("name") else []
                        elif v.get("name") and v["name"] not in v["names"]:
                            v["names"].insert(0, v["name"])
                    self._player_names = data
                else:
                    self._player_names = {}
        except Exception:
            self._player_names = {}

    def _save_player_names(self) -> None:
        try:
            self._player_names_file.write_text(json.dumps(self._player_names, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _remember_player(self, xuid: str, name: str, uuid: str = "", device_id: str | None = None, build_platform: "int | None" = None) -> None:
        """记录一个曾见过的玩家。用 XUID 做唯一标识，改名时保留历史名字，并记下设备号。"""
        x = (xuid or "").strip().lower()
        if not x:
            return
        name = str(name or "").strip()
        entry = self._player_names.get(x)
        now = time.time()
        if entry and entry.get("name") == name:
            entry["seen_at"] = now
            if device_id:
                entry["device_id"] = device_id
            if build_platform is not None:
                entry["build_platform"] = build_platform
            self._save_player_names()
            return
        if entry is None:
            entry = {"name": name, "names": [name] if name else [], "uuid": uuid or "", "device_id": device_id or None, "build_platform": build_platform, "seen_at": now, "created_at": now}
        else:
            names = entry.get("names") or []
            if name and (not names or names[0] != name):
                names = [name] + [n for n in names if n != name]
            entry["name"] = name
            entry["names"] = names[:20]  # 最多保留 20 个历史名
            entry["uuid"] = uuid or entry.get("uuid", "")
            if device_id:
                entry["device_id"] = device_id
            if build_platform is not None:
                entry["build_platform"] = build_platform
            entry["seen_at"] = now
        self._player_names[x] = entry
        self._save_player_names()

    def _player_roster(self) -> list[dict]:
        """返回名册（按最近上线排序），含历史名字，供前端与权限管理使用。"""
        out = []
        for xuid, e in self._player_names.items():
            out.append({
                "xuid": str(xuid).lower(),
                "name": e.get("name") or "",
                "names": e.get("names") or [],
                "uuid": e.get("uuid") or "",
                "device_id": e.get("device_id"),
                "build_platform": e.get("build_platform"),
                "seen_at": e.get("seen_at"),
                "created_at": e.get("created_at"),
            })
        out.sort(key=lambda d: d.get("seen_at") or 0, reverse=True)
        return out

    # ---------- 玩家动态（上下线时间线，持久化到 /data） ----------

    def _load_activity(self) -> None:
        try:
            if self._activity_file.exists():
                data = json.loads(self._activity_file.read_text(encoding="utf-8"))
                self._activity = [d for d in data if isinstance(d, dict)][-2000:] if isinstance(data, list) else []
            else:
                self._activity = []
        except Exception:
            self._activity = []

    def _save_activity(self) -> None:
        try:
            self._activity_file.parent.mkdir(parents=True, exist_ok=True)
            self._activity_file.write_text(
                json.dumps(self._activity[-2000:], ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def _activity_open_session(self, xuid: str) -> dict | None:
        for s in reversed(self._activity):
            if s.get("xuid") == xuid and not s.get("leave_at"):
                return s
        return None

    def _activity_join(self, xuid: str, name: str) -> None:
        x = str(xuid or "").strip().lower()
        if not x:
            return
        existing = self._activity_open_session(x)
        if existing:
            existing["name"] = name or existing.get("name")
            return
        self._activity.append({"xuid": x, "name": name or "", "join_at": time.time(), "leave_at": None})
        del self._activity[:-2000]
        self._save_activity()
        bus.publish({"type": "presence", "data": {"action": "join", "name": name, "xuid": x, "ts": time.time()}})

    def _activity_leave(self, xuid: str, name: str = "") -> None:
        x = str(xuid or "").strip().lower()
        if not x:
            return
        s = self._activity_open_session(x)
        if not s:
            return
        s["leave_at"] = time.time()
        if name:
            s["name"] = name
        self._save_activity()
        bus.publish({"type": "presence", "data": {"action": "leave", "name": s.get("name"), "xuid": x, "ts": time.time()}})

    def _track_presence(self) -> None:
        """对比在线玩家快照记录上下线。机器人掉线重连时不误记「退出」。"""
        if not getattr(tooldelta, "ready", False):
            self._online_prev = None
            return
        current: dict[str, str] = {}
        try:
            for p in tooldelta.players_maintainer.getAllPlayers():
                x = str(getattr(p, "xuid", "") or "").strip().lower()
                if x:
                    current[x] = str(getattr(p, "name", "") or "")
        except Exception:
            return
        if self._online_prev is None:
            # 首次就绪：把已在线的记为“加入”（面板启动时在线）；重连后只重建快照不补记
            if not self._presence_started:
                for x, n in current.items():
                    self._activity_join(x, n)
                self._presence_started = True
            self._online_prev = current
            return
        prev = self._online_prev
        for x, n in current.items():
            if x not in prev:
                self._activity_join(x, n)
                self._gate_on_join(x, n)
        for x, n in prev.items():
            if x not in current:
                self._activity_leave(x, n)
        self._online_prev = current

    def player_activity(self, limit: int = 100) -> list[dict]:
        """返回玩家动态（新的在前）。未结束的会话标 online 并给出已在线时长。"""
        try:
            limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            limit = 100
        now = time.time()
        out: list[dict] = []
        for s in reversed(self._activity):
            join_at = s.get("join_at")
            leave_at = s.get("leave_at")
            duration = ((leave_at or now) - join_at) if join_at else 0
            out.append({
                "xuid": s.get("xuid"),
                "name": s.get("name") or "",
                "join_at": join_at,
                "leave_at": leave_at,
                "online": not leave_at,
                "duration_seconds": int(max(0, duration)),
            })
            if len(out) >= limit:
                break
        return out

    def activity_stats(self) -> dict:
        t = time.localtime()
        try:
            day_start = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
        except Exception:
            day_start = 0
        online = 0
        today = 0
        for s in self._activity:
            if not s.get("leave_at"):
                online += 1
            if (s.get("join_at") or 0) >= day_start:
                today += 1
        return {"total_sessions": len(self._activity), "online": online, "today_sessions": today}

    # ---------- 在线人数采样（曲线/活跃度） ----------

    def _load_samples(self) -> None:
        try:
            if self._samples_file.exists():
                d = json.loads(self._samples_file.read_text(encoding="utf-8"))
                if isinstance(d, list):
                    self._samples = [[float(x[0]), int(x[1])] for x in d if isinstance(x, (list, tuple)) and len(x) == 2][-20000:]
        except Exception:
            self._samples = []

    def _save_samples(self) -> None:
        try:
            self._samples_file.parent.mkdir(parents=True, exist_ok=True)
            self._samples_file.write_text(json.dumps(self._samples[-20000:]), encoding="utf-8")
        except Exception:
            pass

    def _online_count(self) -> int:
        try:
            return len(tooldelta.players_maintainer.getAllPlayers())
        except Exception:
            return 0

    def _sample_online(self, count: int | None = None) -> None:
        """定期/变化时采样一次在线人数。人数变化时加快采样，稳定时每 ~1 分钟一次。"""
        try:
            if count is None:
                count = self._online_count()
            now = time.time()
            changed = int(count) != self._last_sample_count
            if not changed and (now - self._last_sample_ts) < 55:
                return
            if changed and (now - self._last_sample_ts) < 20:
                return
            self._samples.append([now, int(count)])
            self._last_sample_ts = now
            self._last_sample_count = int(count)
            cutoff = now - 7 * 86400
            if self._samples and self._samples[0][0] < cutoff:
                self._samples = [s for s in self._samples if s[0] >= cutoff]
            self._save_samples()
        except Exception:
            pass

    def online_history(self, hours: int = 24) -> dict:
        try:
            hours = max(1, min(int(hours), 168))
        except (TypeError, ValueError):
            hours = 24
        now = time.time()
        start = now - hours * 3600
        pts = [s for s in self._samples if s[0] >= start]
        return {
            "points": pts,
            "current": self._online_count(),
            "peak": max([int(p[1]) for p in pts], default=0),
            "hours": hours,
        }

    # ---------- 进服审核 / 白名单（默认关闭） ----------

    def _load_gate(self) -> None:
        try:
            if self._gate_file.exists():
                d = json.loads(self._gate_file.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    self._gate = {
                        "enabled": bool(d.get("enabled")),
                        "approved": d.get("approved") if isinstance(d.get("approved"), dict) else {},
                        "pending": d.get("pending") if isinstance(d.get("pending"), list) else [],
                        "rejected": d.get("rejected") if isinstance(d.get("rejected"), list) else [],
                        "message": str(d.get("message") or ""),
                    }
        except Exception:
            pass

    def _save_gate(self) -> None:
        try:
            self._gate_file.parent.mkdir(parents=True, exist_ok=True)
            self._gate_file.write_text(json.dumps(self._gate, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    def _bot_name(self) -> str:
        try:
            return str(getattr(tooldelta.game_ctrl, "bot_name", "") or "")
        except Exception:
            return ""

    def gate_state(self) -> dict:
        appr = []
        for k, v in (self._gate.get("approved") or {}).items():
            nm = (v or {}).get("name", "") if isinstance(v, dict) else str(v or "")
            appr.append({"xuid": k, "name": nm})
        appr.sort(key=lambda d: d.get("name") or "~")
        pending = list(self._gate.get("pending") or [])
        pending.sort(key=lambda d: d.get("ts") or 0, reverse=True)
        return {
            "enabled": bool(self._gate.get("enabled")),
            "approved": appr,
            "pending": pending,
            "count": len(appr),
            "message": str(self._gate.get("message") or ""),
            "default_message": GATE_DEFAULT_MESSAGE,
        }

    def gate_set_enabled(self, enabled: bool) -> dict:
        self._gate["enabled"] = bool(enabled)
        self._save_gate()
        if enabled:
            threading.Thread(target=self._gate_import_admins, daemon=True).start()
        return {"ok": True, **self.gate_state()}

    def _gate_import_admins(self) -> None:
        """开启审核时自动把现有管理员和机器人导入白名单，避免把服主锁在门外。"""
        added = 0
        try:
            r = self.permission_list()
            for a in (r.get("data") or []):
                x = str(a.get("xuid") or "").lower()
                if x and x not in self._gate["approved"]:
                    self._gate["approved"][x] = {"name": a.get("name") or ""}
                    added += 1
        except Exception:
            pass
        try:
            bot = self._bot_name()
            for p in tooldelta.players_maintainer.getAllPlayers():
                if str(getattr(p, "name", "")) == bot and getattr(p, "xuid", ""):
                    x = str(p.xuid).lower()
                    if x not in self._gate["approved"]:
                        self._gate["approved"][x] = {"name": bot}
                        added += 1
        except Exception:
            pass
        if added:
            self._save_gate()
            bus.publish({"type": "log", "level": "INFO", "msg": f"进服审核已开启：已导入 {added} 位现有管理员/机器人到白名单"})
            bus.publish({"type": "gate", "data": {"action": "refresh"}})
        self._gate_sweep_online()

    def _gate_sweep_online(self) -> None:
        """开启审核后，把当前在线但不在白名单里的玩家请出（在白名单导入完成后执行）。"""
        try:
            players = list(tooldelta.players_maintainer.getAllPlayers())
        except Exception:
            return
        bot = self._bot_name()
        kicked = 0
        for p in players:
            nm = str(getattr(p, "name", "") or "")
            x = str(getattr(p, "xuid", "") or "").strip().lower()
            if not x or x in (self._gate.get("approved") or {}):
                continue
            if nm and nm == bot:
                continue
            try:
                if p.is_op():
                    self._gate["approved"][x] = {"name": nm}
                    self._save_gate()
                    continue
            except Exception:
                pass
            pend = [it for it in (self._gate.get("pending") or []) if str((it or {}).get("xuid") or "").lower() != x]
            pend.append({"xuid": x, "name": nm, "ts": time.time()})
            self._gate["pending"] = pend[-200:]
            self._save_gate()
            msg = str(self._gate.get("message") or "").strip() or GATE_DEFAULT_MESSAGE
            msg = msg.replace("{player}", nm).replace("{玩家}", nm)
            # 延迟几秒再踢，保证提示语能显示
            self._gate_kick_later(x, nm, msg)
            kicked += 1
            bus.publish({"type": "gate", "data": {"action": "pending", "name": nm, "xuid": x}})
        if kicked:
            bus.publish({"type": "log", "level": "WARNING", "msg": f"进服审核：已将 {kicked} 位不在白名单的在线玩家请出"})

    def gate_approve(self, xuid: str, name: str = "") -> dict:
        x = str(xuid or "").strip().lower()
        if not x:
            return {"ok": False, "error": "缺少玩家标识"}
        self._gate["approved"][x] = {"name": name or ""}
        self._gate["pending"] = [p for p in self._gate.get("pending", []) if str((p or {}).get("xuid") or "").lower() != x]
        self._gate["rejected"] = [p for p in self._gate.get("rejected", []) if str((p or {}).get("xuid") or "").lower() != x]
        self._save_gate()
        bus.publish({"type": "gate", "data": {"action": "approve", "name": name, "xuid": x}})
        return {"ok": True, **self.gate_state()}

    def gate_reject(self, xuid: str, name: str = "") -> dict:
        x = str(xuid or "").strip().lower()
        if not x:
            return {"ok": False, "error": "缺少玩家标识"}
        self._gate["pending"] = [p for p in self._gate.get("pending", []) if str((p or {}).get("xuid") or "").lower() != x]
        self._gate["approved"].pop(x, None)
        rej = [p for p in self._gate.get("rejected", []) if str((p or {}).get("xuid") or "").lower() != x]
        rej.append({"xuid": x, "name": name or "", "ts": time.time()})
        self._gate["rejected"] = rej[-200:]
        self._save_gate()
        bus.publish({"type": "gate", "data": {"action": "reject", "name": name, "xuid": x}})
        return {"ok": True, **self.gate_state()}

    def gate_remove(self, xuid: str) -> dict:
        x = str(xuid or "").strip().lower()
        self._gate["approved"].pop(x, None)
        self._save_gate()
        bus.publish({"type": "gate", "data": {"action": "remove", "xuid": x}})
        return {"ok": True, **self.gate_state()}

    def gate_set_message(self, message: str) -> dict:
        """设置玩家被请出时看到的提示语；留空则用默认。"""
        self._gate["message"] = str(message or "").strip()[:200]
        self._save_gate()
        return {"ok": True, **self.gate_state()}

    def _gate_kick_later(self, xuid: str, name: str, msg: str, delay: float = GATE_KICK_DELAY) -> None:
        """稍等几秒再请出：玩家完全进服后，自定义提示语才显示得出来。"""
        x = str(xuid or "").strip().lower()

        def _worker() -> None:
            try:
                time.sleep(max(0.5, float(delay)))
            except Exception:
                pass
            # 等待期间被批准了，就不再踢
            if x and x in (self._gate.get("approved") or {}):
                return
            try:
                tooldelta.game_ctrl.sendwocmd(f"/kick {_cmd_quote(name)} {msg}")
                bus.publish({"type": "log", "level": "WARNING", "msg": f"进服审核拦截：{name}（待管理员批准）"})
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _gate_on_join(self, xuid: str, name: str) -> None:
        """新玩家上线时按审核规则处理：不在白名单则踢出并记为待审。"""
        if not self._gate.get("enabled"):
            return
        x = str(xuid or "").lower()
        if not x or x in (self._gate.get("approved") or {}):
            return
        if name and name == self._bot_name():
            return
        # 在线且是管理员则自动放行
        try:
            p = tooldelta.players_maintainer.getPlayerByXUID(str(xuid))
            if p is not None and p.is_op():
                self._gate["approved"][x] = {"name": name}
                self._save_gate()
                return
        except Exception:
            pass
        pend = [it for it in (self._gate.get("pending") or []) if str((it or {}).get("xuid") or "").lower() != x]
        pend.append({"xuid": x, "name": name or "", "ts": time.time()})
        self._gate["pending"] = pend[-200:]
        self._save_gate()
        msg = str(self._gate.get("message") or "").strip() or GATE_DEFAULT_MESSAGE
        msg = msg.replace("{player}", name or "").replace("{玩家}", name or "")
        # 稍等几秒再踢：玩家完全进服后提示语才显示得出来
        self._gate_kick_later(xuid, name, msg)
        bus.publish({"type": "gate", "data": {"action": "pending", "name": name, "xuid": x}})

    # ---------- 聊天记录（本地关键词检索，不接 AI） ----------

    def _load_chatlog(self) -> None:
        try:
            if self._chatlog_file.exists():
                lines = self._chatlog_file.read_text(encoding="utf-8", errors="replace").splitlines()[-8000:]
                for line in lines:
                    try:
                        self._chatlog.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            pass

    def _append_chatlog(self, player: str, msg: str, kind: str = "chat", ts: float | None = None) -> None:
        try:
            rec = {"ts": ts or time.time(), "player": player or "", "msg": msg or "", "kind": kind}
            self._chatlog.append(rec)
            self._chatlog_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._chatlog_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            try:
                if self._chatlog_file.stat().st_size > 3_000_000:
                    keep = list(self._chatlog)[-4000:]
                    self._chatlog_file.write_text(
                        "\n".join(json.dumps(r, ensure_ascii=False) for r in keep) + "\n", encoding="utf-8"
                    )
            except Exception:
                pass
        except Exception:
            pass

    def chatlog_search(self, q: str = "", limit: int = 100) -> dict:
        try:
            limit = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            limit = 100
        q = (q or "").strip().lower()
        out: list[dict] = []
        for rec in reversed(self._chatlog):
            if q and q not in str(rec.get("msg", "")).lower() and q not in str(rec.get("player", "")).lower():
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        return {"total": len(self._chatlog), "items": out}

    # ---------- 世界规则状态（面板侧记录，供回显） ----------

    def _load_world_rules(self) -> None:
        try:
            if self._world_rules_file.exists():
                data = json.loads(self._world_rules_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._world_rules = {str(k): str(v) for k, v in data.items()}
        except Exception:
            self._world_rules = {}

    def _save_world_rules(self) -> None:
        try:
            self._world_rules_file.parent.mkdir(parents=True, exist_ok=True)
            self._world_rules_file.write_text(
                json.dumps(self._world_rules, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:
            pass

    def world_rules(self) -> dict:
        return dict(self._world_rules)

    # ---------- 生命周期 ----------

    def _thread_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _launcher_status(self):
        launcher = getattr(tooldelta, "launcher", None)
        if launcher is None:
            return None
        try:
            return launcher.status
        except Exception:
            return None

    def _sync_lifecycle_state(self):
        launcher_status = self._launcher_status()
        with self._lock:
            if launcher_status in (SysStatus.CRASHED_EXIT, SysStatus.FB_LAUNCH_EXC):
                self._state = "error"
            elif launcher_status == SysStatus.NORMAL_EXIT:
                self._state = "stopped"
            elif self._state in ("starting", "running") and not self._thread_alive():
                self._state = "stopped"
            return self._state

    def start(self) -> dict:
        self._sync_lifecycle_state()
        with self._lock:
            if self._state in ("starting", "running"):
                return {"ok": False, "error": "框架已在运行"}
            self._state = "starting"
            self._error = None

        def _run():
            try:
                # 无 TTY 防护：防止框架内 input() 抛 EOFError 导致框架被误判退出
                _patch_stdin_for_web()
                start_tool_delta(LaunchConfig(restart_delay=-1))
            except Exception as e:
                with self._lock:
                    self._error = f"{e}\n{traceback.format_exc()}"
                    self._state = "error"
            finally:
                with self._lock:
                    if self._state != "error":
                        self._state = "stopped"
                bus.publish({"type": "status", "data": self.status()})

        self._thread = threading.Thread(target=_run, name="tooldelta-main", daemon=True)
        self._thread.start()
        self._start_watcher()
        return {"ok": True}

    def _start_watcher(self):
        """轮询 ready 状态，ready 后注册聊天监听并广播状态。"""
        if self._watcher and self._watcher.is_alive():
            return

        def _watch():
            while True:
                time.sleep(0.5)
                try:
                    ready = bool(getattr(tooldelta, "ready", False))
                    if ready:
                        with self._lock:
                            if self._state == "starting":
                                self._state = "running"
                    if ready != self._last_ready:
                        self._last_ready = ready
                        if ready and not self._chat_registered:
                            self._register_chat_listener()
                        bus.publish({"type": "status", "data": self.status()})
                    if ready:
                        self._enforce_blacklist_online()
                        self._track_presence()
                        self._sample_online()
                    if not ready and self._state == "stopped":
                        bus.publish({"type": "status", "data": self.status()})
                        break
                except Exception:
                    pass

        self._watcher = threading.Thread(target=_watch, name="tooldelta-watcher", daemon=True)
        self._watcher.start()

    def stop(self) -> dict:
        state = self._sync_lifecycle_state()
        with self._lock:
            if state in ("idle", "stopped", "error"):
                self._state = "stopped"
                return {"ok": True}
        try:
            if getattr(tooldelta, "ready", False):
                tooldelta.launcher.update_status(SysStatus.NORMAL_EXIT)
            else:
                tooldelta.system_exit("web stop")
        except Exception as e:
            return {"ok": False, "error": str(e)}
        with self._lock:
            self._state = "stopped"
            self._last_ready = False
        # 服务停止后世界规则状态作废，避免误导回显
        self._world_rules = {}
        try:
            if self._world_rules_file.exists():
                self._world_rules_file.unlink()
        except Exception:
            pass
        bus.publish({"type": "status", "data": self.status()})
        return {"ok": True}

    # ---------- 聊天监听 ----------

    def _register_chat_listener(self):
        try:
            hdl = tooldelta.packet_handler

            def _on_text(pkt: dict) -> bool:
                try:
                    name, msg, ensure = get_playername_and_msg_from_text_packet(
                        tooldelta, pkt
                    )
                    tt = pkt.get("TextType")
                    if name and msg:
                        kind = {
                            TextType.TextTypeChat: "chat",
                            TextType.TextTypeWhisper: "whisper",
                            TextType.TextTypeAnnouncement: "announcement",
                        }.get(tt, "chat")
                        bus.publish(
                            {
                                "type": "chat",
                                "data": {
                                    "kind": kind,
                                    "player": name,
                                    "msg": msg,
                                    "verified": bool(ensure),
                                    "ts": time.time(),
                                },
                            }
                        )
                        self._append_chatlog(name, msg, kind)
                    elif tt == TextType.TextTypeTranslation:
                        # 系统/翻译消息也作为 chat 广播（如玩家加入/离开）
                        bus.publish(
                            {
                                "type": "chat",
                                "data": {
                                    "kind": "system",
                                    "player": "",
                                    "msg": mc_translator.translate(
                                        pkt.get("Message", ""), pkt.get("Parameters", [])
                                    ),
                                    "verified": True,
                                    "ts": time.time(),
                                },
                            }
                        )
                except Exception:
                    pass
                return False  # 不拦截，让插件 / GameCtrl 继续处理

            hdl.add_dict_packet_listener(PacketIDS.Text, _on_text, 50)
            self._chat_registered = True
        except Exception:
            pass

    # ---------- 状态 ----------

    def status(self) -> dict:
        self._sync_lifecycle_state()
        with self._lock:
            state = self._state
            error = self._error

        initialized = bool(getattr(tooldelta, "initialized", False))
        launcher = getattr(tooldelta, "launcher", None)

        launcher_status = None
        launcher_label = None
        launch_type = None
        if launcher is not None:
            launch_type = getattr(launcher, "launch_type", None)
            try:
                launcher_status = int(launcher.status)
                launcher_label = _STATUS_LABEL.get(launcher.status, str(launcher.status))
            except Exception:
                pass

        ready = bool(getattr(tooldelta, "ready", False))
        if state in ("idle", "stopped", "error"):
            ready = False

        bot_name = None
        player_names = []
        if ready:
            try:
                bot_name = tooldelta.game_ctrl.bot_name
            except Exception:
                pass
            try:
                player_names = [p.name for p in tooldelta.players_maintainer.getAllPlayers()]
            except Exception:
                pass

        return {
            "state": state,
            "ready": ready,
            "initialized": initialized,
            "launcher_status": launcher_status,
            "launcher_label": launcher_label,
            "launch_type": launch_type,
            "bot_name": bot_name,
            "players": player_names,
            "error": error,
            "world_rules": self.world_rules(),
        }

    # ---------- 玩家 ----------

    def _maintainer(self):
        if not getattr(tooldelta, "ready", False):
            raise RuntimeError("框架尚未就绪")
        return tooldelta.players_maintainer

    def players(self) -> list[dict]:
        pm = self._maintainer()
        out = []
        for p in pm.getAllPlayers():
            self._remember_player(p.xuid, p.name, p.uuid, p.device_id, p.build_platform)
            out.append(_player_to_dict(p))
        return out

    def _xuid_to_names(self) -> dict:
        """构建 xuid -> 玩家名 映射：先名册（含离线），再用在线玩家覆盖。"""
        m = {k: v.get("name") for k, v in self._player_names.items() if v.get("name")}
        try:
            for p in self._maintainer().getAllPlayers():
                x = (p.xuid or "").lower()
                if x:
                    m[x] = p.name
        except Exception:
            pass
        return m

    def _blacklist_kick_reason(self, entry: dict) -> str:
        reason = str(entry.get("reason") or "未填写原因").strip()
        remaining = entry.get("remaining_seconds")
        if remaining is None and entry.get("expires_at"):
            remaining = max(0, int(float(entry["expires_at"]) - time.time()))
        if remaining:
            minutes = max(1, int((int(remaining) + 59) / 60))
            return f"你已被服务器黑名单限制：{reason}，剩余约 {minutes} 分钟"
        return f"你已被服务器黑名单限制：{reason}"

    def enforce_blacklist_once(self, name: str, entry: dict | None = None, xuid: str = "") -> dict:
        player = str(name or "").strip()
        if not player:
            return {"ok": False, "error": "玩家名不能为空"}
        if not getattr(tooldelta, "ready", False):
            return {"ok": True, "skipped": True, "message": "框架尚未就绪，已保存黑名单"}
        active = entry or blacklist_service.find_active(player, xuid)
        if not active:
            return {"ok": True, "skipped": True, "message": "玩家不在黑名单中"}
        try:
            reason = self._blacklist_kick_reason(active)
            cmd = f"/kick {_cmd_quote(player)} {reason}"
            tooldelta.game_ctrl.sendwocmd(cmd)
            result = {"ok": True, "messages": [f"{player} 已被黑名单拦截"]}
            self._record_op("blacklist", f"黑名单拦截 {player}", cmd, result)
            bus.publish({"type": "log", "level": "WARNING", "msg": f"黑名单拦截：{player}"})
            return result
        except Exception as e:
            result = {"ok": False, "error": str(e)}
            self._record_op("blacklist", f"黑名单拦截 {player}", f"/kick {_cmd_quote(player)}", result)
            return result

    def _enforce_blacklist_online(self) -> None:
        try:
            pm = tooldelta.players_maintainer
            now = time.time()
            for p in pm.getAllPlayers():
                name = str(getattr(p, "name", "") or "").strip()
                if not name:
                    continue
                xuid = str(getattr(p, "xuid", "") or "").strip()
                active = blacklist_service.find_active(name, xuid)
                if not active:
                    self._blacklist_kick_until.pop(name.lower(), None)
                    continue
                cooldown_key = name.lower()
                if self._blacklist_kick_until.get(cooldown_key, 0) > now:
                    continue
                self._blacklist_kick_until[cooldown_key] = now + 20
                self.enforce_blacklist_once(name, active, xuid)
        except Exception:
            pass

    def player_detail(self, name: str) -> dict:
        pm = self._maintainer()
        p = pm.getPlayerByName(name)
        if p is None:
            raise KeyError(f"玩家 {name} 不存在或不在线")

        d = _player_to_dict(p)
        d["is_op"] = None
        d["abilities"] = None
        try:
            ab = p.abilities
            d["abilities"] = {
                "build": ab.build,
                "mine": ab.mine,
                "doors_and_switches": ab.doors_and_switches,
                "open_containers": ab.open_containers,
                "attack_players": ab.attack_players,
                "attack_mobs": ab.attack_mobs,
                "operator_commands": ab.operator_commands,
                "teleport": ab.teleport,
                "player_permissions": ab.player_permissions,
                "command_permissions": ab.command_permissions,
            }
            d["is_op"] = ab.command_permissions >= 3
        except Exception:
            pass
        return d

    # ---------- 命令 ----------

    def send_command(self, identity: str, cmd: str, timeout: float = 10) -> dict:
        """Send a Minecraft command or a ToolDelta native console command."""
        cmd = cmd.strip()
        if not cmd:
            return {"ok": False, "error": "命令为空"}

        try:
            if not getattr(tooldelta, "ready", False):
                return {"ok": False, "error": "框架尚未就绪"}
            if identity == "native":
                native_cmd = cmd.removeprefix("/").strip()
                manager = getattr(tooldelta, "cmd_manager", None)
                if manager is None:
                    return {"ok": False, "error": "ToolDelta 原生命令管理器尚未就绪"}
                recognized = any(
                    native_cmd.startswith(prefix)
                    for prefix in getattr(manager, "commands", {})
                )
                manager.execute_cmd(native_cmd)
                return {
                    "ok": True,
                    "success": recognized,
                    "messages": [],
                    "raw": None,
                    "note": "原生命令已提交，输出会显示在下方终端日志。",
                }
            gc = tooldelta.game_ctrl
            if identity == "wo":
                gc.sendwocmd(cmd)
                return {"ok": True, "messages": [], "raw": None}
            if identity == "ws":
                result = gc.sendwscmd_with_resp(cmd, timeout)
            elif identity == "cmd":
                result = gc.sendcmd_with_resp(cmd, timeout)
            elif identity == "ai":
                if not hasattr(gc.launcher, "sendaicmd"):
                    gc.sendaicmd(cmd)
                    return {"ok": True, "messages": [], "raw": None, "note": "该接入点不支持魔法命令返回"}
                result = gc.sendaicmd_with_resp(cmd, timeout)
            else:
                return {"ok": False, "error": "未知命令身份"}

            messages = [
                mc_translator.translate(o.Message, o.Parameters)
                for o in result.OutputMessages
            ]
            return {
                "ok": True,
                "success": bool(result.SuccessCount),
                "messages": messages,
                "raw": result.as_dict,
            }
        except TimeoutError:
            return {"ok": False, "error": "命令返回超时"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- 服务器权限管理（/permission，走 AI 魔法命令通道） ----------

    def permission_send(self, cmd: str, timeout: float = 12) -> dict:
        """低层：以 AI 魔法命令身份下发任意 permission 命令，返回结构化输出。

        permission 是网易租赁服服务端命令（含离线操作），必须走 sendaicmd 通道，
        不能走游戏内 sendcmd（会误发到游戏聊天/普通命令执行环境）。
        """
        return self.send_command("ai", cmd, timeout)

    def _ensure_command_output_listener(self) -> None:
        """注册一次性的抓包监听，用于读取 AI 魔法命令的回显。

        `/permission` 只能经 AI 魔法命令通道下发，而该通道在部分接入点上是单向的
        （sendaicmdonly，不返回）。服务端可能把结果作为 CommandOutput 或 Text 数据包回传，
        这里把这两类包都收集起来解析（不限文字类型，避免漏掉命令反馈）。
        """
        if getattr(self, "_opkt_registered", False):
            return
        self._opkt_lock = threading.Lock()
        self._opkts = deque(maxlen=60)
        self._opkt_event = threading.Event()
        self._opkt_registered = True
        ph = getattr(tooldelta, "packet_handler", None)
        if ph is None:
            return

        def _collect(pk):
            try:
                with self._opkt_lock:
                    self._opkts.append(pk)
                self._opkt_event.set()
            except Exception:
                pass
            return False

        for pid in (PacketIDS.CommandOutput, PacketIDS.Text):
            try:
                ph.add_dict_packet_listener(pid, _collect, 88)
            except Exception:
                pass

    def permission_list(self) -> dict:
        """列出服务器所有管理员（XUID），含离线玩家，并回填最新名/历史名/设备号。"""
        if not getattr(tooldelta, "ready", False):
            return {"ok": False, "error": "服务器未运行：请先在控制台启动服务，等机器人上线后再刷新"}
        import re

        self._ensure_command_output_listener()
        with self._opkt_lock:
            self._opkts.clear()
        self._opkt_event.clear()
        r = self.send_command("ai", "/permission list", 6)
        if not r.get("ok"):
            return r
        # 命令输出可能分包返回，等第一个包后再多收一小会儿
        self._opkt_event.wait(6)
        time.sleep(0.5)
        with self._opkt_lock:
            pkts = list(self._opkts)
        texts: list[str] = []
        types: list[str] = []
        for pk in pkts:
            try:
                tt = pk.get("TextType")
                if tt is not None:
                    types.append(f"Text#{tt}")
                msg = pk.get("Message")
                if msg:
                    try:
                        texts.append(str(mc_translator.translate(msg, pk.get("Parameters"))))
                    except Exception:
                        texts.append(str(msg))
                for o in (pk.get("OutputMessages") or []):
                    om = o.get("Message")
                    if om:
                        try:
                            texts.append(str(mc_translator.translate(om, o.get("Parameters"))))
                        except Exception:
                            texts.append(str(om))
                    types.append("CmdOut")
                ds = pk.get("DataSet")
                if ds:
                    texts.append(str(ds))
            except Exception:
                pass
        blob = " ".join(texts)
        # 服务端回显是一段 JSON：
        #   {"command":"permissions","result":[{"permission":"operator","xuid":"..."}, ...]}
        #   {"command":"ops","result":["xuid", ...]}
        # 只有 permission == "operator" 的才是管理员。
        def _extract_json(s: str):
            a = s.find("{")
            b = s.rfind("}")
            if a < 0 or b <= a:
                return None
            try:
                return json.loads(s[a:b + 1])
            except Exception:
                return None

        ordered: list[str] = []
        ops_fallback: list[str] = []
        for t in texts:
            obj = _extract_json(t)
            if not isinstance(obj, dict):
                continue
            cmd = obj.get("command")
            res = obj.get("result")
            if cmd == "permissions" and isinstance(res, list):
                for item in res:
                    if isinstance(item, dict) and item.get("permission") == "operator":
                        x = str(item.get("xuid") or "").lower()
                        if x:
                            ordered.append(x)
            elif cmd == "ops" and isinstance(res, list):
                for x in res:
                    x = str(x).lower()
                    if x:
                        ops_fallback.append(x)
        if not ordered and ops_fallback:
            ordered = ops_fallback
        if not ordered and not texts:
            return {"ok": False, "error": "未从服务器读到管理员回显（可能服务器忙或接入点限制），稍后再刷新试试"}
        xus = list(dict.fromkeys(ordered))
        known = self._xuid_to_names()
        online = set()
        try:
            for p in self._maintainer().getAllPlayers():
                if p.xuid:
                    online.add(str(p.xuid).lower())
        except Exception:
            pass
        admins = []
        for x in xus:
            entry = self._player_names.get(x)
            admins.append({
                "xuid": x,
                "name": known.get(x),
                "names": (entry.get("names") if entry else None) or [],
                "device_id": entry.get("device_id") if entry else None,
                "online": x in online,
            })
        return {
            "ok": True,
            "data": admins,
            "packets": len(pkts),
            "types": types[:40],
            "texts": texts[:20],
            "messages": r.get("messages"),
        }

    def permission_set(self, xuid: str, flags: str) -> dict:
        """设置 XUID 的权限位（8 位 0/1 串），含离线。"""
        xuid = str(xuid).strip().lstrip(".")
        flags = str(flags).strip().lstrip(".")
        if not xuid or not flags:
            return {"ok": False, "error": "请填写 XUID 与权限位"}
        return self.send_command("ai", f"/permission setbyxuid .{xuid} .{flags}", 12)

    def permission_revoke(self, xuid: str) -> dict:
        """撤销某个 XUID 的管理员权限，含离线。"""
        xuid = str(xuid).strip().lstrip(".")
        if not xuid:
            return {"ok": False, "error": "请填写 XUID"}
        return self.send_command("ai", f"/permission del .{xuid}", 12)

    def broadcast(self, text: str) -> dict:
        """控制台身份广播（tellraw，带 [控制台] 前缀）。"""
        return self.send_chat("console", text)

    def send_chat(self, identity: str, text: str, custom_name: str = "") -> dict:
        """以不同身份向游戏内发言。

        identity ∈ {console, bot, custom}：
          - console: tellraw 广播，带 [控制台] 前缀
          - bot:     以机器人身份 /say，游戏内显示为机器人发言
          - custom:  tellraw 广播，使用用户填写的身份名前缀
        """
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "内容为空"}
        custom_name = (custom_name or "").strip()[:24]
        try:
            gc = tooldelta.game_ctrl
            if identity == "bot":
                # /say 由机器人以操作员身份执行，游戏内显示为机器人名发言
                gc.sendwocmd(f"/say {text}")
            elif identity == "custom":
                if not custom_name:
                    return {"ok": False, "error": "请填写自定义身份名"}
                gc.say_to("@a", f"[§d{custom_name}§r] §f{text}")
            else:
                gc.say_to("@a", f"[§b控制台§r] §3{text}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- 原生管理 ----------

    def _record_op(self, kind: str, title: str, cmd: str, result: dict) -> None:
        self._ops.appendleft({
            "ts": time.time(),
            "kind": kind,
            "title": title,
            "cmd": cmd,
            "ok": bool(result.get("ok")),
            "success": result.get("success"),
            "error": result.get("error"),
            "messages": result.get("messages", []),
        })

    def operation_log(self) -> list[dict]:
        return list(self._ops)

    def managed_command(self, kind: str, title: str, cmd: str, identity: str = "ws", timeout: float = 10) -> dict:
        result = self.send_command(identity, cmd, timeout)
        self._record_op(kind, title, cmd, result)
        return result

    def player_action(self, action: str, data: dict) -> dict:
        player = str(data.get("player", "")).strip()
        if not player:
            return {"ok": False, "error": "请选择玩家"}
        target = _cmd_quote(player)
        action = str(action or "").strip()
        if action == "kick":
            reason = str(data.get("reason", "由 Web 面板移出")).strip() or "由 Web 面板移出"
            return self.managed_command("player", f"踢出 {player}", f"/kick {target} {reason}")
        if action == "op":
            return self.managed_command("player", f"授予 OP {player}", f"/op {target}")
        if action == "deop":
            return self.managed_command("player", f"取消 OP {player}", f"/deop {target}")
        if action == "gamemode":
            mode = str(data.get("mode", "survival")).strip()
            if mode not in ("survival", "creative", "adventure", "spectator", "s", "c", "a"):
                return {"ok": False, "error": "游戏模式无效"}
            return self.managed_command("player", f"设置模式 {player}", f"/gamemode {mode} {target}")
        if action == "tp_player":
            dest = str(data.get("target", "")).strip()
            if not dest:
                return {"ok": False, "error": "请选择传送目标"}
            return self.managed_command("player", f"传送 {player}", f"/tp {target} {_cmd_quote(dest)}")
        if action == "tp_pos":
            x = str(data.get("x", "")).strip()
            y = str(data.get("y", "")).strip()
            z = str(data.get("z", "")).strip()
            if not x or not y or not z:
                return {"ok": False, "error": "请填写完整坐标"}
            return self.managed_command("player", f"传送坐标 {player}", f"/tp {target} {x} {y} {z}")
        if action == "give":
            item = str(data.get("item", "")).strip().replace("minecraft:", "")
            count = int(data.get("count") or 1)
            if not item:
                return {"ok": False, "error": "请填写物品 ID"}
            count = max(1, min(count, 2304))
            return self.managed_command("player", f"给予物品 {player}", f"/give {target} {item} {count}")
        if action == "clear":
            return self.managed_command("player", f"清空背包 {player}", f"/clear {target}")
        if action == "kill":
            return self.managed_command("player", f"击杀 {player}", f"/kill {target}")
        return {"ok": False, "error": "未知玩家操作"}

    def world_action(self, action: str, data: dict) -> dict:
        action = str(action or "").strip()
        if action == "time":
            value = str(data.get("value", "day")).strip()
            if value not in ("day", "night", "noon", "midnight", "sunrise", "sunset"):
                return {"ok": False, "error": "时间参数无效"}
            return self.managed_command("world", f"设置时间 {value}", f"/time set {value}")
        if action == "weather":
            value = str(data.get("value", "clear")).strip()
            if value not in ("clear", "rain", "thunder"):
                return {"ok": False, "error": "天气参数无效"}
            return self.managed_command("world", f"设置天气 {value}", f"/weather {value}")
        if action == "difficulty":
            value = str(data.get("value", "normal")).strip()
            if value not in ("peaceful", "easy", "normal", "hard", "p", "e", "n", "h"):
                return {"ok": False, "error": "难度参数无效"}
            result = self.managed_command("world", f"设置难度 {value}", f"/difficulty {value}")
            if result.get("ok") and result.get("success") is not False:
                self._world_rules["difficulty"] = value
                self._save_world_rules()
            return result
        if action == "gamerule":
            rule = str(data.get("rule", "")).strip()
            value = str(data.get("value", "")).strip()
            allowed = {
                "keepInventory", "mobGriefing", "doDaylightCycle", "doWeatherCycle",
                "doMobSpawning", "doImmediateRespawn", "showCoordinates", "commandBlockOutput",
                "sendCommandFeedback", "doFireTick", "pvp", "showDeathMessages",
            }
            if rule not in allowed:
                return {"ok": False, "error": "游戏规则不在白名单中"}
            if value not in ("true", "false"):
                return {"ok": False, "error": "游戏规则值必须是 true/false"}
            result = self.managed_command("world", f"设置规则 {rule}", f"/gamerule {rule} {value}")
            if result.get("ok") and result.get("success") is not False:
                self._world_rules[f"rule:{rule}"] = value
                self._save_world_rules()
            return result
        return {"ok": False, "error": "未知世界操作"}

    def command_template(self, data: dict) -> dict:
        cmd = str(data.get("cmd", "")).strip()
        title = str(data.get("title", "命令模板")).strip() or "命令模板"
        identity = str(data.get("identity", "ws")).strip()
        if identity not in ("wo", "ws", "cmd", "ai"):
            identity = "ws"
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        return self.managed_command("template", title, cmd, identity=identity, timeout=10)

    def player_inventory(self, name: str) -> dict:
        """查询玩家背包内容（实时，走 codebuilder_actorinfo）。"""
        pm = self._maintainer()
        p = pm.getPlayerByName(name)
        if p is None:
            raise KeyError(f"玩家 {name} 不存在或不在线")
        raw = game_utils.queryPlayerInventory(p.safe_name)
        inv = raw.get("inventory", {}) if isinstance(raw, dict) else {}
        slots = []
        for s in inv.get("slots", []) or []:
            if not s:
                slots.append(None)
                continue
            slots.append({
                "namespace": s.get("namespace", ""),
                "id": s.get("id", ""),
                "displayName": _item_display_name(s.get("id", "")),
                "customName": _item_custom_name(s),
                "stackSize": s.get("stackSize", 0),
                "maxStackSize": s.get("maxStackSize", 0),
                "aux": s.get("aux", 0),
                "freeStackSize": s.get("freeStackSize", 0),
                "enchantments": s.get("enchantments", []) or [],
            })
        return {
            "first": inv.get("first", 0),
            "last": inv.get("last", 0),
            "slotCount": inv.get("slotCount", 0),
            "slots": slots,
        }

    def player_position(self, name: str) -> dict:
        """查询玩家实时位置（走 querytarget）。"""
        pm = self._maintainer()
        p = pm.getPlayerByName(name)
        if p is None:
            raise KeyError(f"玩家 {name} 不存在或不在线")
        data = game_utils.getPos(p.name)
        return {
            "dimension": data.get("dimension"),
            "position": data.get("position", {}),
            "yRot": data.get("yRot"),
        }


manager = FrameManager()
