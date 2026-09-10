"""Flask 应用：REST API + WebSocket 推送。

路由:
    GET  /                    -> 面板前端 (static/index.html)
    GET  /api/status          -> 框架状态
    GET  /api/players         -> 玩家列表
    GET  /api/players/<name>  -> 玩家详情
    POST /api/start           -> 启动框架
    POST /api/stop            -> 停止框架
    POST /api/command         -> 发送命令 {identity, cmd, timeout}
    POST /api/broadcast       -> 游戏内广播 {text}
    WS   /ws                  -> 推送日志/聊天/状态流
"""
import os
import json
import time
import threading
import queue

from flask import Flask, jsonify, redirect, request, send_from_directory, session
from flask_sock import Sock

from . import auth_service
from . import bridge
from . import config_service
from . import plugin_service
from . import plugin_config_service
from . import file_service
from . import blacklist_service
from .bus import bus
from .paths import STATIC_DIR, ensure_root_cwd, ensure_dirs

# 任意启动方式下都把 cwd 切到项目根，使框架的相对路径配置正确定位
ensure_root_cwd()
ensure_dirs()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    creds = auth_service.ensure_credentials()
    app.secret_key = os.environ.get("SHENYI_PANEL_SECRET") or creds.get("password_hash") or os.urandom(32)
    sock = Sock(app)

    @app.before_request
    def require_login():
        if os.environ.get("SHENYI_PANEL_AUTH", "1").lower() in ("0", "false", "no", "off"):
            return None
        path = request.path or "/"
        if path in ("/login", "/api/auth/login") or path.startswith("/style.css") or path.startswith("/app.js"):
            return None
        if path.startswith("/assets/") or path.startswith("/items/") or path.startswith("/blocks/") or path.startswith("/item_meta.json") or path.startswith("/item_icons.json") or path.startswith("/item_names.json"):
            return None
        if session.get("panel_logged_in"):
            return None
        if path.startswith("/api/") or path == "/ws":
            return jsonify({"ok": False, "error": "请先登录"}), 401
        return redirect("/login")

    # ---------- 页面 ----------

    @app.get("/login")
    def login_page():
        return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>神翼面板 · 登录</title>
<style>
:root{--text:#263047;--muted:#74809a;--accent:#8d7cff;--accent2:#6fb7ff;--red:#eb5b75}
*{box-sizing:border-box}body{min-height:100vh;margin:0;display:grid;place-items:center;padding:18px;background:radial-gradient(circle at 20% 0%,#dfe7ff 0,transparent 36%),radial-gradient(circle at 90% 80%,#dbfff4 0,transparent 32%),#f7f8ff;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.login{width:min(420px,100%);padding:28px;border:1px solid rgba(255,255,255,.68);border-radius:30px;background:rgba(255,255,255,.62);box-shadow:0 24px 80px rgba(107,121,168,.2);backdrop-filter:blur(24px) saturate(145%);-webkit-backdrop-filter:blur(24px) saturate(145%)}
.logo{width:54px;height:54px;border-radius:18px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),var(--accent2));color:white;font-weight:900;box-shadow:0 16px 36px rgba(141,124,255,.28);margin-bottom:18px}
h1{margin:0 0 8px;font-size:28px}.sub{margin:0 0 22px;color:var(--muted);line-height:1.7}
label{display:block;color:var(--muted);font-size:13px;margin:14px 0 7px}input{width:100%;height:46px;border-radius:16px;border:1px solid rgba(124,133,168,.2);background:rgba(255,255,255,.72);padding:0 14px;font-size:15px;color:var(--text);outline:none}input:focus{border-color:rgba(141,124,255,.55)}
button{width:100%;height:48px;margin-top:18px;border:0;border-radius:16px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:white;font-weight:800;font-size:15px;cursor:pointer;box-shadow:0 14px 30px rgba(141,124,255,.26)}
.msg{min-height:18px;margin-top:12px;color:var(--red);font-size:13px}.tip{margin-top:18px;padding:12px 14px;border:1px dashed rgba(124,133,168,.24);border-radius:16px;color:var(--muted);font-size:12px;line-height:1.6}
</style></head><body><form class="login" id="login-form"><div class="logo">SY</div><h1>登录神翼面板</h1><p class="sub">请输入容器启动时生成的账号密码。登录后即可管理当前实例。</p><label>账号</label><input id="username" autocomplete="username" autofocus /><label>密码</label><input id="password" type="password" autocomplete="current-password" /><button>进入面板</button><div class="msg" id="msg"></div><div class="tip">提示：首次启动生成的账号密码会显示在 Docker 启动日志中，也会保存在实例数据目录。</div></form><script>
document.getElementById('login-form').onsubmit=async(e)=>{e.preventDefault();const msg=document.getElementById('msg');msg.textContent='正在登录…';const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value,password:password.value})});const j=await r.json().catch(()=>({ok:false,error:'登录失败'}));if(j.ok) location.href='/'; else msg.textContent=j.error||'账号或密码错误';};
</script></body></html>"""

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/manage")
    @app.route("/manage/")
    @app.route("/manage/<path:section>")
    def manage_root(section=None):
        # 旧运营中心路由统一重定向到世界页
        return redirect("/world")

    @app.route("/<path:path>")
    def static_files(path):
        file_path = os.path.join(STATIC_DIR, path)
        if os.path.isfile(file_path):
            return send_from_directory(STATIC_DIR, path)
        return send_from_directory(STATIC_DIR, "index.html")

    # ---------- API ----------

    @app.post("/api/auth/login")
    def api_auth_login():
        data = request.get_json(silent=True) or {}
        if auth_service.verify(data.get("username", ""), data.get("password", "")):
            session["panel_logged_in"] = True
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "账号或密码错误"}), 401

    @app.post("/api/auth/logout")
    def api_auth_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/status")
    def api_status():
        return jsonify({"ok": True, "data": bridge.manager.status()})

    @app.get("/api/players")
    def api_players():
        try:
            return jsonify({"ok": True, "data": bridge.manager.players()})
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e), "data": []}), 409

    @app.get("/api/players/<name>")
    def api_player_detail(name):
        try:
            return jsonify({"ok": True, "data": bridge.manager.player_detail(name)})
        except KeyError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 409

    @app.get("/api/roster")
    def api_roster():
        # 玩家名册：XUID -> 当前名 + 历史名（改名可追溯），供权限/黑名单/历史玩家使用
        try:
            return jsonify({"ok": True, "data": bridge.manager._player_roster()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/activity")
    def api_activity():
        # 玩家动态：上下线时间线（含在线时长），持久化在 /data
        try:
            limit = request.args.get("limit", 100)
            return jsonify({
                "ok": True,
                "data": bridge.manager.player_activity(limit),
                "stats": bridge.manager.activity_stats(),
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/online-history")
    def api_online_history():
        # 在线人数采样曲线
        try:
            return jsonify({"ok": True, "data": bridge.manager.online_history(request.args.get("hours", 24))})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/gate")
    def api_gate():
        # 进服审核 / 白名单状态
        try:
            return jsonify({"ok": True, **bridge.manager.gate_state()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/gate/toggle")
    def api_gate_toggle():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.gate_set_enabled(bool(data.get("enabled"))))

    @app.post("/api/gate/approve")
    def api_gate_approve():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.gate_approve(data.get("xuid"), data.get("name", "")))

    @app.post("/api/gate/reject")
    def api_gate_reject():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.gate_reject(data.get("xuid"), data.get("name", "")))

    @app.post("/api/gate/remove")
    def api_gate_remove():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.gate_remove(data.get("xuid")))

    @app.post("/api/gate/message")
    def api_gate_message():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.gate_set_message(data.get("message", "")))

    @app.get("/api/chatlog")
    def api_chatlog():
        # 聊天记录检索（本地关键词，不接 AI）
        try:
            return jsonify({"ok": True, "data": bridge.manager.chatlog_search(request.args.get("q", ""), request.args.get("limit", 100))})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/start")
    def api_start():
        check = config_service.startup_check()
        if not check["ok"]:
            return jsonify(check), 409
        return jsonify(bridge.manager.start())

    @app.post("/api/stop")
    def api_stop():
        return jsonify(bridge.manager.stop())

    @app.post("/api/command")
    def api_command():
        data = request.get_json(silent=True) or {}
        identity = data.get("identity", "ws")
        cmd = data.get("cmd", "")
        timeout = float(data.get("timeout", 10))
        return jsonify(bridge.manager.send_command(identity, cmd, timeout))

    @app.post("/api/broadcast")
    def api_broadcast():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.broadcast(data.get("text", "")))

    @app.post("/api/chat")
    def api_chat():
        """游戏内发言，identity ∈ {console, bot, custom}。"""
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.send_chat(
            data.get("identity", "console"),
            data.get("text", ""),
            data.get("custom_name", ""),
        ))

    # ---------- 原生服务器管理 ----------

    @app.post("/api/server/player_action")
    def api_server_player_action():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.player_action(data.get("action", ""), data))

    @app.post("/api/server/world_action")
    def api_server_world_action():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.world_action(data.get("action", ""), data))

    @app.post("/api/server/template")
    def api_server_template():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.command_template(data))

    @app.get("/api/server/ops")
    def api_server_ops():
        return jsonify({"ok": True, "data": bridge.manager.operation_log()})

    @app.get("/api/permissions/list")
    def api_permissions_list():
        return jsonify(bridge.manager.permission_list())

    @app.post("/api/permissions/set")
    def api_permissions_set():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.permission_set(
            data.get("xuid", ""), data.get("flags", "")))

    @app.post("/api/permissions/revoke")
    def api_permissions_revoke():
        data = request.get_json(silent=True) or {}
        return jsonify(bridge.manager.permission_revoke(data.get("xuid", "")))

    @app.get("/api/blacklist")
    def api_blacklist():
        include_expired = request.args.get("include_expired", "0") in ("1", "true", "yes")
        return jsonify(blacklist_service.list_entries(include_expired=include_expired))

    @app.post("/api/blacklist/add")
    def api_blacklist_add():
        data = request.get_json(silent=True) or {}
        xuid = data.get("xuid", "")
        result = blacklist_service.add_entry(
            data.get("name") or data.get("player", ""),
            data.get("reason", ""),
            data.get("duration_minutes", 0),
            data.get("operator", "Web 面板"),
            xuid,
        )
        if result.get("ok") and data.get("kick_now", True):
            bridge.manager.enforce_blacklist_once(result["data"]["name"], result["data"], xuid)
        return jsonify(result)

    @app.post("/api/blacklist/remove")
    def api_blacklist_remove():
        data = request.get_json(silent=True) or {}
        return jsonify(blacklist_service.remove_entry(
            data.get("id", ""),
            data.get("name") or data.get("player", ""),
        ))

    @app.get("/api/players/<name>/inventory")
    def api_player_inventory(name):
        try:
            return jsonify({"ok": True, "data": bridge.manager.player_inventory(name)})
        except KeyError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 409
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/players/<name>/position")
    def api_player_position(name):
        try:
            return jsonify({"ok": True, "data": bridge.manager.player_position(name)})
        except KeyError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 409
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ---------- 启动配置 ----------

    @app.get("/api/config/schema")
    def api_config_schema():
        return jsonify({"ok": True, "data": config_service.schema()})

    @app.get("/api/config")
    def api_config_get():
        return jsonify({"ok": True, "data": config_service.get_config()})

    @app.post("/api/config")
    def api_config_save():
        data = request.get_json(silent=True) or {}
        return jsonify(config_service.save_config(data))

    # ---------- 插件管理 ----------

    @app.get("/api/plugins")
    def api_plugins():
        return jsonify({"ok": True, "data": plugin_service.list_plugins()})

    @app.post("/api/plugins/<path:name>/toggle")
    def api_plugin_toggle(name):
        return jsonify(plugin_service.toggle_plugin(name))

    @app.post("/api/plugins/<path:name>/delete")
    def api_plugin_delete(name):
        return jsonify(plugin_service.delete_plugin(name))

    @app.post("/api/plugins/<path:name>/update")
    def api_plugin_update(name):
        return jsonify(plugin_service.update_plugin(name))

    @app.post("/api/plugins/update_all")
    def api_plugin_update_all():
        return jsonify(plugin_service.update_all())

    @app.get("/api/plugin-configs")
    def api_plugin_configs():
        return jsonify(plugin_config_service.list_configs())

    @app.get("/api/plugin-configs/read")
    def api_plugin_config_read():
        return jsonify(plugin_config_service.get_config(request.args.get("path", "")))

    @app.post("/api/plugin-configs/save")
    def api_plugin_config_save():
        data = request.get_json(silent=True) or {}
        return jsonify(plugin_config_service.save_config(
            data.get("path", ""),
            data.get("values", {}),
        ))

    # ---------- 插件市场 ----------

    @app.get("/api/market/search")
    def api_market_search():
        rule = request.args.get("rule", "all")
        kw = request.args.get("kw", "")
        return jsonify(plugin_service.market_search(rule, kw))

    @app.get("/api/market/plugin/<plugin_id>")
    def api_market_detail(plugin_id):
        return jsonify(plugin_service.market_plugin_detail(plugin_id))

    @app.get("/api/market/package/<path:pkg_id>")
    def api_market_package_detail(pkg_id):
        return jsonify(plugin_service.market_package_detail(pkg_id))

    @app.post("/api/market/download_plugin")
    def api_market_dl_plugin():
        data = request.get_json(silent=True) or {}
        return jsonify(plugin_service.market_download_plugin(data.get("plugin_id", "")))

    @app.post("/api/market/download_package")
    def api_market_dl_package():
        data = request.get_json(silent=True) or {}
        return jsonify(plugin_service.market_download_package(data.get("pkg_id", "")))

    @app.get("/api/market/doc/<plugin_id>")
    def api_market_doc(plugin_id):
        return jsonify(plugin_service.market_doc(plugin_id))

    # ---------- 文件管理 ----------

    @app.get("/api/files")
    def api_files_list():
        rel = request.args.get("path", "")
        page = request.args.get("page", 1)
        page_size = request.args.get("page_size", 100)
        return jsonify(file_service.list_dir(rel, page=page, page_size=page_size))

    @app.get("/api/files/read")
    def api_files_read():
        rel = request.args.get("path", "")
        return jsonify(file_service.read_file(rel))

    @app.post("/api/files/write")
    def api_files_write():
        data = request.get_json(silent=True) or {}
        return jsonify(file_service.write_file(data.get("path", ""), data.get("content", "")))

    @app.post("/api/files/mkdir")
    def api_files_mkdir():
        data = request.get_json(silent=True) or {}
        return jsonify(file_service.mkdir(data.get("path", "")))

    @app.post("/api/files/delete")
    def api_files_delete():
        data = request.get_json(silent=True) or {}
        return jsonify(file_service.delete(data.get("path", "")))

    @app.post("/api/files/rename")
    def api_files_rename():
        data = request.get_json(silent=True) or {}
        return jsonify(file_service.rename(data.get("path", ""), data.get("new_name", "")))

    @app.post("/api/files/upload")
    def api_files_upload():
        rel_dir = request.form.get("path", "")
        files = request.files.getlist("files")
        if not files:
            return jsonify({"ok": False, "error": "没有收到文件"})
        uploaded, errors = [], []
        for f in files:
            data = f.read()
            result = file_service.upload(rel_dir, f.filename or "", data)
            if result.get("ok"):
                uploaded.append(result["data"])
            else:
                errors.append(f"{f.filename}: {result.get('error', '失败')}")
        ok = bool(uploaded)
        return jsonify({
            "ok": ok,
            "uploaded": uploaded,
            "errors": errors,
            "error": errors[0] if not ok and errors else (None if ok else "上传失败"),
        })

    @app.post("/api/files/extract")
    def api_files_extract():
        data = request.get_json(silent=True) or {}
        return jsonify(file_service.extract_archive(data.get("path", "")))

    # ---------- WebSocket ----------

    @sock.route("/ws")
    def ws(ws):
        q = bus.subscribe()
        try:
            while True:
                try:
                    item = q.get(timeout=15)
                except queue.Empty:
                    continue
                ws.send(json.dumps(item, ensure_ascii=False))
        except Exception:
            pass
        finally:
            bus.unsubscribe(q)

    return app
