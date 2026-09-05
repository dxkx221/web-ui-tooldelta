"""文件管理服务：安全地浏览/编辑运行数据文件。

安全约束：
- 只允许访问白名单里的配置、插件、日志目录，避免把源码暴露给用户。
- 二进制文件以 base64 返回 + 标记 is_binary，前端只读展示。
- 上传/解压同样限制在白名单目录内，压缩包解压防路径穿越。
"""
import base64
import io
import os
import shutil
import zipfile
from pathlib import Path

from .paths import (
    CFG_FILE,
    FBTOKEN_FILE,
    LOG_DIR,
    PLUGIN_CFG_DIR,
    PLUGIN_DATA_DIR,
    PLUGIN_DIR,
    safe_join,
)

# 文本编辑的大小上限（字节），超过则只读不提供编辑
TEXT_EDIT_MAX = 512 * 1024
# 读取返回的大小上限（字节），超过截断
READ_MAX = 2 * 1024 * 1024

# 上传大小上限（字节）：200MB，覆盖插件包/整合包场景
UPLOAD_MAX = 200 * 1024 * 1024
# 解压单文件数量/总体积上限，防压缩炸弹
EXTRACT_MAX_FILES = 5000
EXTRACT_MAX_BYTES = 500 * 1024 * 1024

# 支持的压缩包扩展名（仅安全 zip 格式）
ARCHIVE_EXTS = {".zip"}
TEXT_EXTS = {
    ".py", ".js", ".ts", ".html", ".css", ".json", ".yml", ".yaml", ".toml",
    ".md", ".txt", ".cfg", ".ini", ".sh", ".bat", ".csv", ".xml", ".log",
    ".proto", ".lock", ".gitignore", ".env", ".sig", ".crt", ".php", ".sql",
}

MANAGED_ROOTS = {
    "ToolDelta基本配置.json": CFG_FILE,
    "fbtoken": FBTOKEN_FILE,
    "插件文件": PLUGIN_DIR,
    "插件配置文件": PLUGIN_CFG_DIR,
    "插件数据文件": PLUGIN_DATA_DIR,
    "日志文件": LOG_DIR,
}

MANAGED_ROOT_ORDER = [
    "ToolDelta基本配置.json",
    "fbtoken",
    "插件文件",
    "插件配置文件",
    "插件数据文件",
    "日志文件",
]

MANAGED_DIR_ROOTS = {"插件文件", "插件配置文件", "插件数据文件", "日志文件"}
MANAGED_FILE_ROOTS = {"ToolDelta基本配置.json", "fbtoken"}
PROTECTED_ROOTS = set(MANAGED_ROOTS)


def _clean_rel(rel: str) -> str:
    return (rel or "").strip().strip("/").strip("\\").replace("\\", "/")


def _resolve(rel: str) -> Path | None:
    """把相对路径解析到可管理根目录内；越界或非白名单返回 None。"""
    rel = _clean_rel(rel)
    if not rel:
        return None

    top, _, child_rel = rel.partition("/")
    root = MANAGED_ROOTS.get(top)
    if root is None:
        return None
    if not child_rel:
        return root
    if root.is_file():
        return None
    return safe_join(root, child_rel)


def _entry_dict(path: Path, name: str | None = None) -> dict:
    stat = path.stat()
    return {
        "name": name if name is not None else path.name,
        "is_dir": path.is_dir(),
        "size": stat.st_size if not path.is_dir() else None,
        "mtime": stat.st_mtime,
    }


def upload(rel_dir: str, filename: str, data: bytes) -> dict:
    """把上传文件写入白名单目录（rel_dir 必须是目录）。data 为完整字节。"""
    filename = (filename or "").strip().replace("\\", "/")
    if not filename or filename in (".", "..") or filename.startswith("/"):
        return {"ok": False, "error": "非法的文件名"}
    # 只取最后一段，禁止子路径穿越
    basename = filename.rsplit("/", 1)[-1].strip()
    if not basename or basename in (".", ".."):
        return {"ok": False, "error": "非法的文件名"}

    rel = _clean_rel(rel_dir)
    target_dir = None
    if rel:
        target_dir = _resolve(rel)
    else:
        # 根视图：只能上传到第一个目录型根（插件文件）——前端应始终带目录，这里兜底拒绝
        return {"ok": False, "error": "请先进入具体文件夹再上传"}
    if target_dir is None:
        return {"ok": False, "error": "只能上传到配置、插件、日志等运行目录"}
    if not target_dir.exists() or not target_dir.is_dir():
        return {"ok": False, "error": "目标目录不存在"}

    if len(data) > UPLOAD_MAX:
        return {"ok": False, "error": f"文件过大（超过 {UPLOAD_MAX // 1024 // 1024}MB）"}
    if not data:
        return {"ok": False, "error": "空文件"}

    dest = safe_join(target_dir, basename)
    if dest is None:
        return {"ok": False, "error": "非法路径"}
    try:
        dest.write_bytes(data)
        return {"ok": True, "data": _entry_dict(dest)}
    except OSError as e:
        return {"ok": False, "error": f"写入失败：{e}"}


def extract_archive(rel: str) -> dict:
    """解压 zip 到自身所在目录；防路径穿越 + 防压缩炸弹。"""
    rel = _clean_rel(rel)
    target = _resolve(rel)
    if target is None:
        return {"ok": False, "error": "只能操作配置、插件、日志等运行文件"}
    if not target.exists() or target.is_dir():
        return {"ok": False, "error": "文件不存在"}
    if target.suffix.lower() not in ARCHIVE_EXTS:
        return {"ok": False, "error": "仅支持 .zip 压缩包解压"}

    out_dir = target.parent
    try:
        zf = zipfile.ZipFile(target)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "压缩包已损坏或不是 zip 格式"}

    infos = zf.infolist()
    if len(infos) > EXTRACT_MAX_FILES:
        return {"ok": False, "error": "压缩包内文件过多，已拒绝"}
    total = 0
    for info in infos:
        total += info.file_size
        if total > EXTRACT_MAX_BYTES:
            return {"ok": False, "error": "压缩包解压后体积过大，已拒绝"}
        # 防路径穿越
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            return {"ok": False, "error": f"压缩包内含非法路径：{info.filename}"}

    extracted = 0
    try:
        for info in infos:
            name = info.filename.replace("\\", "/").strip("/")
            if not name:
                continue
            dest = safe_join(out_dir, name)
            if dest is None:
                raise ValueError(f"非法路径：{info.filename}")
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            extracted += 1
    except Exception as e:
        return {"ok": False, "error": f"解压中断：{e}"}
    finally:
        zf.close()

    return {"ok": True, "data": {"extracted": extracted, "path": _virtual_path(out_dir)}}


def _virtual_path(path: Path) -> str:
    resolved = path.resolve()
    for name, root in MANAGED_ROOTS.items():
        root_resolved = root.resolve()
        if resolved == root_resolved:
            return name
        if root_resolved in resolved.parents:
            return f"{name}/{resolved.relative_to(root_resolved).as_posix()}"
    return path.name


def _root_entries() -> list[dict]:
    entries = []
    for name in MANAGED_ROOT_ORDER:
        path = MANAGED_ROOTS[name]
        if name in MANAGED_FILE_ROOTS and not path.exists():
            continue
        if name in MANAGED_FILE_ROOTS and path.is_dir():
            continue
        if name in MANAGED_DIR_ROOTS and not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        stat = path.stat()
        entries.append({
            "name": name,
            "is_dir": path.is_dir(),
            "size": stat.st_size if not path.is_dir() else None,
            "mtime": stat.st_mtime,
        })
    return entries


def list_dir(rel: str, page: int = 1, page_size: int = 100) -> dict:
    try:
        page = max(1, int(page))
        page_size = max(10, min(int(page_size), 500))
    except (TypeError, ValueError):
        page, page_size = 1, 100

    rel = _clean_rel(rel)
    if not rel:
        entries = _root_entries()
        total = len(entries)
        return {
            "ok": True,
            "data": {
                "path": "",
                "entries": entries,
                "total": total,
                "page": 1,
                "page_size": page_size,
                "total_pages": 1,
            },
        }

    target = _resolve(rel)
    if target is None:
        return {"ok": False, "error": "只能访问配置、插件、日志等运行文件"}
    if not target.exists():
        return {"ok": False, "error": "路径不存在"}
    if not target.is_dir():
        return {"ok": False, "error": "不是目录"}

    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            stat = child.stat()
            entries.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": stat.st_size if not child.is_dir() else None,
                "mtime": stat.st_mtime,
            })
    except PermissionError as e:
        return {"ok": False, "error": f"无权限访问：{e}"}

    total = len(entries)
    total_pages = max(1, -(-total // page_size))  # 向上取整
    page = min(page, total_pages)
    start = (page - 1) * page_size
    page_entries = entries[start:start + page_size]

    return {
        "ok": True,
        "data": {
            "path": _virtual_path(target),
            "entries": page_entries,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    }


def read_file(rel: str) -> dict:
    target = _resolve(rel)
    if target is None:
        return {"ok": False, "error": "只能读取配置、插件、日志等运行文件"}
    if not target.exists():
        return {"ok": False, "error": "文件不存在"}
    if target.is_dir():
        return {"ok": False, "error": "是目录，无法读取"}

    size = target.stat().st_size
    if size > READ_MAX:
        return {"ok": False, "error": f"文件过大（{size} 字节），不提供在线读取"}

    ext = target.suffix.lower()
    is_text = ext in TEXT_EXTS or size == 0
    try:
        data = target.read_bytes()
    except PermissionError as e:
        return {"ok": False, "error": f"无权限读取：{e}"}

    if is_text:
        try:
            content = data.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            try:
                content = data.decode("gbk")
                encoding = "gbk"
            except UnicodeDecodeError:
                is_text = False
                content = None
                encoding = None

    if is_text:
        return {
            "ok": True,
            "data": {
                "path": _virtual_path(target),
                "is_binary": False,
                "encoding": encoding,
                "size": size,
                "content": content,
                "editable": size <= TEXT_EDIT_MAX,
            },
        }
    # 二进制：base64
    return {
        "ok": True,
        "data": {
            "path": _virtual_path(target),
            "is_binary": True,
            "size": size,
            "content": base64.b64encode(data).decode("ascii"),
            "editable": False,
        },
    }


def write_file(rel: str, content: str) -> dict:
    target = _resolve(rel)
    if target is None:
        return {"ok": False, "error": "只能写入配置、插件、日志等运行文件"}
    if target.exists() and target.is_dir():
        return {"ok": False, "error": "目标是目录，无法写入"}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (content or "").encode("utf-8")
        if len(data) > TEXT_EDIT_MAX:
            return {"ok": False, "error": "内容过大，拒绝写入"}
        target.write_bytes(data)
        return {"ok": True, "data": {"path": _virtual_path(target)}}
    except PermissionError as e:
        return {"ok": False, "error": f"无权限写入：{e}"}


def mkdir(rel: str) -> dict:
    target = _resolve(rel)
    if target is None:
        return {"ok": False, "error": "只能在插件、配置、日志目录内新建文件夹"}
    if target.exists():
        return {"ok": False, "error": "目录已存在"}
    try:
        target.mkdir(parents=True, exist_ok=False)
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "error": str(e)}


def delete(rel: str) -> dict:
    rel = _clean_rel(rel)
    if rel in PROTECTED_ROOTS:
        return {"ok": False, "error": "系统入口不能删除"}
    target = _resolve(rel)
    if target is None:
        return {"ok": False, "error": "只能删除配置、插件、日志等运行文件"}
    if not target.exists():
        return {"ok": False, "error": "路径不存在"}
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "error": str(e)}


def rename(rel: str, new_name: str) -> dict:
    rel = _clean_rel(rel)
    if rel in PROTECTED_ROOTS:
        return {"ok": False, "error": "系统入口不能重命名"}
    target = _resolve(rel)
    if target is None:
        return {"ok": False, "error": "只能重命名配置、插件、日志等运行文件"}
    if not target.exists():
        return {"ok": False, "error": "路径不存在"}
    new_name = (new_name or "").strip()
    if not new_name or "/" in new_name or "\\" in new_name or new_name in (".", ".."):
        return {"ok": False, "error": "非法的新名称"}
    dest = target.parent / new_name
    if dest.exists():
        return {"ok": False, "error": "目标名称已存在"}
    try:
        target.rename(dest)
        return {"ok": True}
    except OSError as e:
        return {"ok": False, "error": str(e)}
