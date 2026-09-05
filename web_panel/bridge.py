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
from .paths import PANEL_DATA_DIR


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
        return [_player_to_dict(p) for p in pm.getAllPlayers()]

    def _blacklist_kick_reason(self, entry: dict) -> str:
        reason = str(entry.get("reason") or "未填写原因").strip()
        remaining = entry.get("remaining_seconds")
        if remaining is None and entry.get("expires_at"):
            remaining = max(0, int(float(entry["expires_at"]) - time.time()))
        if remaining:
            minutes = max(1, int((int(remaining) + 59) / 60))
            return f"你已被服务器黑名单限制：{reason}，剩余约 {minutes} 分钟"
        return f"你已被服务器黑名单限制：{reason}"

    def enforce_blacklist_once(self, name: str, entry: dict | None = None) -> dict:
        player = str(name or "").strip()
        if not player:
            return {"ok": False, "error": "玩家名不能为空"}
        if not getattr(tooldelta, "ready", False):
            return {"ok": True, "skipped": True, "message": "框架尚未就绪，已保存黑名单"}
        active = entry or blacklist_service.find_active(player)
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
                active = blacklist_service.find_active(name)
                if not active:
                    self._blacklist_kick_until.pop(name.lower(), None)
                    continue
                cooldown_key = name.lower()
                if self._blacklist_kick_until.get(cooldown_key, 0) > now:
                    continue
                self._blacklist_kick_until[cooldown_key] = now + 20
                self.enforce_blacklist_once(name, active)
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
