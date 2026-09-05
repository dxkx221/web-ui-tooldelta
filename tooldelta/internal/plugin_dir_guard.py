"""
插件目录守卫 — 实时监控 插件文件/ToolDelta类式插件 目录
禁止出现包含"导入"、"导入器"等关键词的文件夹
"""

import os
import time
import threading
import shutil

FORBIDDEN_KEYWORDS = ("导入", "导入器", "导入工具", "importer", "import_tool")
WATCH_DIR = "插件文件/ToolDelta类式插件"
WARNING_MSG = "§c本程序禁止出现一切导入操作，此操作可能导致机器人账号封禁。"


class PluginDirGuard:
    def __init__(self):
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="plugin-dir-guard")
        self._thread.start()

    def stop(self):
        self._running = False

    def _watch_loop(self):
        """主循环：每 1 秒扫描一次"""
        while self._running:
            self._scan_and_purge()
            time.sleep(1)

    def _scan_and_purge(self):
        if not os.path.isdir(WATCH_DIR):
            return
        try:
            with os.scandir(WATCH_DIR) as entries:
                for entry in entries:
                    if not entry.is_dir():
                        continue
                    name_lower = entry.name.lower()
                    for keyword in FORBIDDEN_KEYWORDS:
                        if keyword.lower() in name_lower:
                            self._nuke(entry.path)
                            break
        except PermissionError:
            pass
        except Exception:
            pass

    def _nuke(self, dir_path):
        try:
            shutil.rmtree(dir_path, ignore_errors=True)
            from tooldelta.utils import fmts
            fmts.print_err(WARNING_MSG)
        except Exception:
            pass


# --- 主动拦阻层：覆盖常用下载库的函数 ---
_original_makedirs = os.makedirs
_original_rename = os.rename


def _is_forbidden(name: str) -> bool:
    name_lower = name.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if kw.lower() in name_lower:
            return True
    return False


def _is_under_watch(path: str) -> bool:
    """检查路径是否在监控目录下"""
    abs_path = os.path.abspath(path)
    abs_watch = os.path.abspath(WATCH_DIR)
    try:
        common = os.path.commonpath([abs_path, abs_watch])
        return common == abs_watch
    except ValueError:
        return False


def _patched_makedirs(name, mode=0o777, exist_ok=False):
    if _is_under_watch(name):
        parts = os.path.abspath(name).replace(os.path.abspath(WATCH_DIR), "").strip(os.sep)
        if parts and _is_forbidden(parts):
            from tooldelta.utils import fmts
            fmts.print_err(WARNING_MSG)
            raise PermissionError(f"禁止创建导入类文件夹: {name}")
    return _original_makedirs(name, mode, exist_ok)


def _patched_rename(src, dst):
    if _is_under_watch(dst) and _is_forbidden(os.path.basename(dst)):
        from tooldelta.utils import fmts
        fmts.print_err(WARNING_MSG)
        raise PermissionError(f"禁止重命名为导入类文件夹: {dst}")
    return _original_rename(src, dst)


def install_hooks():
    """安装全局拦截钩子"""
    os.makedirs = _patched_makedirs
    os.rename = _patched_rename
    # 拦截 shutil.move / shutil.copytree 等
    shutil._orig_move = shutil.move
    shutil._orig_copytree = shutil.copytree

    def _patched_move(src, dst, *a, **kw):
        if _is_under_watch(dst) and _is_forbidden(os.path.basename(dst)):
            from tooldelta.utils import fmts
            fmts.print_err(WARNING_MSG)
            raise PermissionError(f"禁止移动为导入类文件夹: {dst}")
        return shutil._orig_move(src, dst, *a, **kw)

    def _patched_copytree(src, dst, *a, **kw):
        if _is_under_watch(dst) and _is_forbidden(os.path.basename(dst)):
            from tooldelta.utils import fmts
            fmts.print_err(WARNING_MSG)
            raise PermissionError(f"禁止复制为导入类文件夹: {dst}")
        return shutil._orig_copytree(src, dst, *a, **kw)

    shutil.move = _patched_move
    shutil.copytree = _patched_copytree
