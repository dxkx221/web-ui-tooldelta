"""ToolDelta Web 面板启动入口。

用法:
    python web_run.py

可选参数:
    --host 127.0.0.1   监听地址 (默认 127.0.0.1)
    --port 5100        监听端口 (默认 5100)
"""
import os
import sys
import logging
from pathlib import Path

# 保证工作目录为项目根，使 tooldelta 的相对路径配置 (ToolDelta基本配置.json / fbtoken / 插件文件 等) 正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web_panel import auth_service  # noqa: E402
from web_panel.app import create_app  # noqa: E402
from web_panel.paths import PANEL_DATA_DIR  # noqa: E402


def _parse_args(argv):
    host, port = "127.0.0.1", 5100
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--host" and i + 1 < len(argv):
            host, i = argv[i + 1], i + 2
        elif a == "--port" and i + 1 < len(argv):
            port, i = int(argv[i + 1]), i + 2
        else:
            i += 1
    return host, port


def _public_url(host: str, port: int, instance_id: str | None = None) -> str:
    creds = auth_service.public_credentials()
    if creds.get("public_url"):
        return str(creds["public_url"]).rstrip("/")
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
    if instance_id and root_domain:
        return f"https://{instance_id}.{root_domain}"
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{shown_host}:{port}"


def _quiet_runtime_logs() -> Path:
    log_dir = PANEL_DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "panel.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(file_handler)

    werkzeug = logging.getLogger("werkzeug")
    werkzeug.disabled = True
    werkzeug.setLevel(logging.ERROR)
    return log_file


def _print_startup_summary(host: str, port: int, log_file: Path) -> None:
    creds = auth_service.public_credentials()
    public_url = _public_url(host, port, creds.get("instance_id"))
    lines = [
        "",
        "========================================",
        "神翼面板已启动",
        "",
        f"访问地址：{public_url}",
        f"登录入口：{public_url}/login",
        f"实例编号：{creds['instance_id']}",
        "",
        f"账号：{creds['username']}",
        f"密码：{creds['password']}",
        "",
        f"凭据文件：{creds['file']}",
        f"运行日志：{log_file}",
        "========================================",
        "",
    ]
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    host, port = _parse_args(sys.argv)
    log_file = _quiet_runtime_logs()
    app = create_app()
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *args, **kwargs: None
    except Exception:
        pass
    _print_startup_summary(host, port, log_file)
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
