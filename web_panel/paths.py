"""统一路径解析：全部基于本文件绝对定位，不依赖当前工作目录。

这样无论从哪个目录启动（Windows / Linux / 服务器 / systemd / docker），
配置、fbtoken、插件、日志等相对路径都能正确定位到项目根。
"""
import os
from pathlib import Path

# web_panel/ 所在目录
PANEL_DIR = Path(__file__).resolve().parent

# 项目根目录（web_panel 的上一级，含 tooldelta/、main.py、web_run.py 等）
PROJECT_ROOT = PANEL_DIR.parent

# 核心文件
CFG_FILE = PROJECT_ROOT / "ToolDelta基本配置.json"
FBTOKEN_FILE = PROJECT_ROOT / "fbtoken"

# 目录（与框架 tooldelta.constants 保持一致）
PLUGIN_DIR = PROJECT_ROOT / "插件文件"
CLASSIC_PLUGIN_DIR = PROJECT_ROOT / "插件文件" / "ToolDelta类式插件"
PLUGIN_CFG_DIR = PROJECT_ROOT / "插件配置文件"
PLUGIN_DATA_DIR = PROJECT_ROOT / "插件数据文件"
LOG_DIR = PROJECT_ROOT / "日志文件"
PANEL_DATA_DIR = PROJECT_ROOT / "web_panel_data"

# 静态资源
STATIC_DIR = PANEL_DIR / "static"


def ensure_dirs() -> None:
    """确保关键目录存在。"""
    for d in (PLUGIN_DIR, CLASSIC_PLUGIN_DIR, PLUGIN_CFG_DIR, PLUGIN_DATA_DIR, LOG_DIR, PANEL_DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)


def ensure_root_cwd() -> None:
    """把当前工作目录切到项目根（框架内部用相对路径 Path("插件文件") 等）。

    在 import tooldelta 之前调用一次，即可让框架的相对路径配置在任何启动方式
    （web_run.py / flask run / gunicorn / systemd）下都正确定位到项目根。
    """
    cwd = os.getcwd()
    if os.path.abspath(cwd) != os.path.abspath(str(PROJECT_ROOT)):
        os.chdir(PROJECT_ROOT)


def is_windows() -> bool:
    return os.name == "nt"


def safe_join(root: Path, rel: str) -> Path | None:
    """把用户提供的相对路径安全解析到 root 内；越界返回 None（防目录穿越）。"""
    try:
        target = (root / rel).resolve()
    except (OSError, ValueError):
        return None
    root_resolved = root.resolve()
    if target == root_resolved or root_resolved in target.parents:
        return target
    return None


# 供外部导入的常量集合（避免重复硬编码路径字符串）
__all__ = [
    "PANEL_DIR",
    "PROJECT_ROOT",
    "CFG_FILE",
    "FBTOKEN_FILE",
    "PLUGIN_DIR",
    "CLASSIC_PLUGIN_DIR",
    "PLUGIN_CFG_DIR",
    "PLUGIN_DATA_DIR",
    "LOG_DIR",
    "PANEL_DATA_DIR",
    "STATIC_DIR",
    "ensure_dirs",
    "ensure_root_cwd",
    "safe_join",
    "is_windows",
]
