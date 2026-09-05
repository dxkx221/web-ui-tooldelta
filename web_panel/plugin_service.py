"""插件管理 / 插件市场服务：把 CLI 的交互式操作封装成 Web API。

复用 tooldelta.plugin_manager.plugin_manager 与 tooldelta.plugin_market.market 两个单例，
但绕开它们的 input() 交互，直接调用底层方法。
"""
import re
from tooldelta.plugin_manager import plugin_manager, PluginManager
from tooldelta.plugin_market import market, PluginMarket
from tooldelta.plugin_load import PluginRegData
from tooldelta.utils import fmts


def _ver_tuple(ver: str):
    """把版本字符串解析成数字元组，用于语义化比较。
    解析不了时返回 None（由调用方退化为字符串比较）。
    """
    if ver is None:
        return None
    nums = re.findall(r"\d+", str(ver))
    if not nums:
        return None
    tup = tuple(int(n) for n in nums[:4])
    # 补齐到 4 段，方便比较
    return tup + (0,) * (4 - len(tup))


def _ver_gt(a: str, b: str) -> bool:
    """语义化版本比较：a 是否比 b 新。
    数字段优先；无法解析时退回归一化字符串比较（忽略大小写与 v 前缀）。
    """
    ta, tb = _ver_tuple(a), _ver_tuple(b)
    if ta is not None and tb is not None:
        return ta > tb
    na = str(a or "").strip().lower().lstrip("v")
    nb = str(b or "").strip().lower().lstrip("v")
    return na > nb


def _market_tree_safe() -> dict:
    """取市场树；失败返回空 dict，不抛异常。"""
    try:
        return market.get_market_tree().get("MarketPlugins", {})
    except Exception:
        return {}


def _is_running() -> bool:
    try:
        from .bridge import manager
        status = manager.status()
        return status.get("state") in ("starting", "running")
    except Exception:
        return False


def _post_change(message: str, data=None) -> dict:
    return {
        "ok": True,
        "data": data,
        "needs_restart": _is_running(),
        "message": message,
        "next_steps": [
            "已更新本地插件文件",
            "如果插件生成了配置文件，可以到「插件配置」里填写配置项",
            "如果 ToolDelta 正在运行，请停止后重新启动让插件状态生效",
            "回到插件管理页确认插件是否启用",
        ],
    }


def _reg_to_dict(p: PluginRegData) -> dict:
    return {
        "name": p.name,
        "version": p.version_str,
        "author": p.author,
        "plugin_type": p.plugin_type,
        "plugin_type_str": p.plugin_type_str,
        "description": p.description,
        "pre_plugins": p.pre_plugins,
        "plugin_id": p.plugin_id,
        "is_registered": p.is_registered,
        "is_enabled": p.is_enabled,
    }


def list_plugins() -> list[dict]:
    """列出已安装插件；附 has_update（市场最新版本比本地新才为 True）。"""
    try:
        datas = plugin_manager.get_all_plugin_datas()
    except Exception as e:
        return []
    market_datas = _market_tree_safe()
    out = []
    for p in datas:
        d = _reg_to_dict(p)
        s_data = market_datas.get(p.plugin_id)
        if s_data and p.version_str:
            latest = str(s_data.get("version", ""))
            d["latest_version"] = latest
            d["has_update"] = _ver_gt(latest, str(p.version_str))
        else:
            d["latest_version"] = ""
            d["has_update"] = False
        out.append(d)
    return out


def _installed_names() -> set[str]:
    """已安装插件的名字集合（用于市场页判断是否已装）。"""
    try:
        return {p.name for p in plugin_manager.get_all_plugin_datas()}
    except Exception:
        return set()


def _installed_ids() -> set[str]:
    try:
        return {p.plugin_id for p in plugin_manager.get_all_plugin_datas() if p.plugin_id}
    except Exception:
        return set()


def _package_install_state(plugin_ids: list[str]) -> dict:
    installed_ids = _installed_ids()
    installed_names = _installed_names()
    installed = []
    missing = []
    for plugin_id in plugin_ids:
        try:
            plugin_data = market.get_plugin_data_from_market(plugin_id)
            ok = plugin_id in installed_ids or plugin_data.name in installed_names
            item = {"id": plugin_id, "name": plugin_data.name}
        except Exception:
            ok = plugin_id in installed_ids or plugin_id in installed_names
            item = {"id": plugin_id, "name": plugin_id}
        (installed if ok else missing).append(item)
    total = len(plugin_ids)
    count = len(installed)
    return {
        "installed_count": count,
        "total_count": total,
        "is_installed": total > 0 and count == total,
        "is_partial_installed": 0 < count < total,
        "installed_plugins": installed,
        "missing_plugins": missing,
    }


def toggle_plugin(name: str) -> dict:
    """启用/禁用插件（改文件夹名 +disabled）。"""
    datas = plugin_manager.get_all_plugin_datas()
    target = next((p for p in datas if p.name == name), None)
    if target is None:
        return {"ok": False, "error": f"插件 {name} 不存在"}
    try:
        from tooldelta.constants import PLUGIN_TYPE_MAPPING
        parent_dir = PLUGIN_TYPE_MAPPING[target.plugin_type]
        plugin_manager._toggle_plugin(target, parent_dir)
        plugin_manager.push_plugin_reg_data(target)
        action = "启用" if target.is_enabled else "禁用"
        return _post_change(f"插件已{action}；如果框架正在运行，需要重启后生效。", _reg_to_dict(target))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def delete_plugin(name: str) -> dict:
    """删除插件（rmtree，无交互）。"""
    import shutil
    datas = plugin_manager.get_all_plugin_datas()
    target = next((p for p in datas if p.name == name), None)
    if target is None:
        return {"ok": False, "error": f"插件 {name} 不存在"}
    try:
        dir_path = target.dir
        if dir_path.is_dir():
            shutil.rmtree(dir_path)
        target.is_deleted = True
        if hasattr(plugin_manager, "_plugin_datas_cache"):
            plugin_manager._plugin_datas_cache = []
        return _post_change("插件文件已删除；如果框架正在运行，需要停止后重新启动才会卸载内存中的旧插件。")
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_update(plugin_id: str) -> dict:
    """检查插件最新版本。"""
    try:
        latest = market.get_latest_plugin_version(plugin_id)
        return {"ok": True, "latest": ".".join(str(i) for i in latest)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def update_plugin(name: str) -> dict:
    """从市场更新单个插件（先比版本，已最新则不下载）。"""
    datas = plugin_manager.get_all_plugin_datas()
    target = next((p for p in datas if p.name == name), None)
    if target is None:
        return {"ok": False, "error": f"插件 {name} 不存在"}
    try:
        s_data = _market_tree_safe().get(target.plugin_id)
        if s_data is not None and target.version_str:
            latest = str(s_data.get("version", ""))
            if not _ver_gt(latest, str(target.version_str)):
                return {"ok": True, "message": f"插件 {name} 已是最新版本 v{target.version_str}，无需更新。"}
        plugin_manager.update_plugin_from_market(target)
        return _post_change(f"插件 {name} 已更新；如果框架正在运行，需要重启后生效。", _reg_to_dict(target))
    except Exception as e:
        return {"ok": False, "error": str(e)}


def update_all() -> dict:
    """更新所有可更新插件（非交互，绕开 CLI 的 input()）。

    CLI 的 update_all_plugins 内部有 input()，Web 后台线程会卡死，
    故这里直接复制其「找差异 → 逐个 update_plugin_from_market」逻辑，去掉交互。
    版本差异用语义化比较（数字段），避免格式不同导致的假更新。
    """
    try:
        datas = plugin_manager.get_all_plugin_datas()
        market_datas = market.get_market_tree()["MarketPlugins"]
        updated = []
        errors = []
        for p in datas:
            s_data = market_datas.get(p.plugin_id)
            if s_data is None:
                continue
            if p.version_str and _ver_gt(str(s_data.get("version", "")), str(p.version_str)) and p.is_enabled:
                try:
                    plugin_manager.update_plugin_from_market(p)
                    updated.append(p.name)
                except Exception as e:
                    errors.append(f"{p.name}: {e}")
        msg = "没有发现需要更新的插件" if not updated else f"已更新 {len(updated)} 个插件"
        return _post_change(msg, {"updated": updated, "errors": errors})
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------- 插件市场 ----------

def _market_search(raw_rule: str, kw: str = "") -> list[dict]:
    """按规则搜索市场。raw_rule ∈ {name, author, id, all}。"""
    try:
        market_tree = market.get_market_tree()
        plugin_ids_map = market.get_plugin_id_name_map()
    except Exception as e:
        return []

    show_list = [
        (i, j) if i.startswith("[pkg]") else ("[pkg]" + i, j)
        for i, j in market_tree["Packages"].items()
    ] + list(market_tree["MarketPlugins"].items())

    out = []
    kw = (kw or "").strip().lower()
    for plugin_id, data in show_list:
        if raw_rule == "name":
            pname = plugin_id if plugin_id.startswith("[pkg]") else data["name"]
            if kw in pname.lower():
                out.append(_market_item(plugin_id, data))
        elif raw_rule == "author":
            if kw in data["author"].lower():
                out.append(_market_item(plugin_id, data))
        elif raw_rule == "id":
            if kw in plugin_id.lower():
                out.append(_market_item(plugin_id, data))
        else:
            out.append(_market_item(plugin_id, data))
    return out


def _market_item(plugin_id: str, data: dict) -> dict:
    is_pkg = plugin_id.startswith("[pkg]")
    item = {
        "id": plugin_id,
        "is_package": is_pkg,
        "name": plugin_id if is_pkg else data.get("name", plugin_id),
        "version": data.get("version", ""),
        "author": data.get("author", ""),
        "description": data.get("description", ""),
    }
    if is_pkg:
        plugin_ids = data.get("plugin-ids", []) or data.get("plugin_ids", [])
        item.update(_package_install_state(plugin_ids))
    return item


def market_search(rule: str, kw: str) -> dict:
    """搜索市场，返回 {ok, data, total}。data 为结果列表，total 为总数。

    已安装插件标记 is_installed=True，供前端显示「已安装」而非「下载安装」。
    """
    installed = _installed_names()
    installed_ids = _installed_ids()
    items = _market_search(rule, kw)
    for it in items:
        if not it["is_package"]:
            it["is_installed"] = it["name"] in installed or it["id"] in installed_ids
    return {"ok": True, "data": items, "total": len(items)}


def market_package_detail(pkg_id: str) -> dict:
    """整合包详情，含包内插件安装进度。"""
    try:
        pack = market.get_package_data_from_market(pkg_id)
        state = _package_install_state(pack.plugin_ids)
        return {
            "ok": True,
            "data": {
                "id": pkg_id,
                "name": pack.name,
                "version": pack.version,
                "author": pack.author,
                "description": pack.description,
                "plugin_ids": pack.plugin_ids,
                **state,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def market_plugin_detail(plugin_id: str) -> dict:
    """插件详情（用于下载前展示）。"""
    try:
        plugin_data = market.get_plugin_data_from_market(plugin_id)
        item = _reg_to_dict(plugin_data)
        # 是否已安装
        item["is_installed"] = plugin_data.name in _installed_names() or plugin_data.plugin_id in _installed_ids()
        # 是否有文档
        try:
            ftree = market.get_plugin_filetree(plugin_data.name)
            item["has_doc"] = ("readme.txt" in ftree) or ("readme.md" in ftree)
        except Exception:
            item["has_doc"] = False
        return {"ok": True, "data": item}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def market_download_plugin(plugin_id: str) -> dict:
    """下载单个插件（含前置）。"""
    try:
        plugin_data = market.get_plugin_data_from_market(plugin_id)
        pres = market.download_plugin(plugin_data)
        names = [p.name for p in pres]
        return _post_change(
            f"已下载安装 {plugin_data.name}，共 {len(names)} 个插件（含前置）。",
            {"installed": names, "plugin": _reg_to_dict(plugin_data)},
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}


def market_download_package(pkg_id: str) -> dict:
    """下载整合包。pkg_id 形如 [pkg]xxx。"""
    try:
        import asyncio
        from tooldelta.plugin_market import (
            REMOTE_PLUGIN_CONFIG_DIR,
            REMOTE_PLUGIN_DATA_DIR,
            TOOLDELTA_PLUGIN_CFG_DIR,
            TOOLDELTA_PLUGIN_DATA_DIR,
            thread_gather,
            unfold_directory_dict,
            url_join,
            urlmethod,
        )

        pack = market.get_package_data_from_market(pkg_id)
        plugins = thread_gather([
            (market.get_plugin_data_from_market, (i,)) for i in pack.plugin_ids
        ])
        ftree = market.get_market_filetree()
        plugin_config_files = ftree.get(url_join(pack.name, REMOTE_PLUGIN_CONFIG_DIR), {})
        plugin_data_files = ftree.get(url_join(pack.name, REMOTE_PLUGIN_DATA_DIR), {})
        if isinstance(plugin_config_files, int):
            plugin_config_files = {}
        if isinstance(plugin_data_files, int):
            plugin_data_files = {}

        downloads = []
        skipped = []
        for cfgfile_path in unfold_directory_dict(plugin_config_files):
            local = TOOLDELTA_PLUGIN_CFG_DIR / cfgfile_path
            if local.is_file():
                skipped.append(str(local))
                continue
            downloads.append((
                url_join(market.plugin_market_content_url, pack.name, REMOTE_PLUGIN_CONFIG_DIR, cfgfile_path),
                local,
            ))
        for datafile_path in unfold_directory_dict(plugin_data_files):
            local = TOOLDELTA_PLUGIN_DATA_DIR / datafile_path
            if local.is_file():
                skipped.append(str(local))
                continue
            downloads.append((
                url_join(market.plugin_market_content_url, pack.name, REMOTE_PLUGIN_DATA_DIR, datafile_path),
                local,
            ))
        for _, local in downloads:
            local.parent.mkdir(parents=True, exist_ok=True)
        if downloads:
            asyncio.run(urlmethod.download_file_urls(downloads))

        installed = []
        for plugin_data in plugins:
            installed.extend(p.name for p in market.download_plugin(plugin_data))
        installed = list(dict.fromkeys(installed))
        return _post_change(
            f"整合包 {pack.name.replace('[pkg]', '')} 下载完成，共安装 {len(installed)} 个插件。",
            {"plugin_ids": pack.plugin_ids, "installed": installed, "skipped_existing_files": skipped},
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}


def market_doc(plugin_id: str) -> dict:
    """获取插件文档内容。"""
    try:
        plugin_data = market.get_plugin_data_from_market(plugin_id)
        ftree = market.get_plugin_filetree(plugin_data.name)
        if "readme.md" in ftree:
            url = market.plugin_market_content_url.rstrip("/") + "/" + plugin_data.name + "/readme.md"
            import requests
            resp = requests.get(url, timeout=10)
            return {"ok": True, "markdown": True, "content": resp.text}
        elif "readme.txt" in ftree:
            url = market.plugin_market_content_url.rstrip("/") + "/" + plugin_data.name + "/readme.txt"
            import requests
            resp = requests.get(url, timeout=10)
            return {"ok": True, "markdown": False, "content": resp.text}
        else:
            return {"ok": False, "error": "该插件没有文档"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
