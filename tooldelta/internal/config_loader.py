import os
import getpass
from typing import TYPE_CHECKING
from ..constants import tooldelta_cfg, tooldelta_cli
from ..utils import cfg, urlmethod, sys_args, fbtokenFix, if_token, fmts
from .launch_cli import (
    FrameNeOmegaLauncher,
    FrameNeOmgAccessPoint,
    FrameNeOmgAccessPointRemote,
    FrameEulogistLauncher,
    FrameFateArk,
    FrameFateArkIndirect,
    FrameTanGameAccessPoint,
    LAUNCHERS,
    ACCESS_POINT_LAUNCHERS,
)

if TYPE_CHECKING:
    from tooldelta import ToolDelta


"所有启动器框架类型"
LAUNCHERS_SHOWN: list[tuple[str, type[LAUNCHERS]]] = [
    ("§7NeOmega 框架 (NeOmega 模式)", FrameNeOmgAccessPoint),
    (
        "§7NeOmega 框架 (NeOmega 连接模式，需要先启动对应的 neOmega 接入点)",
        FrameNeOmgAccessPointRemote,
    ),
    (
        "§7NeOmega 框架 (NeOmega 并行模式，同时运行NeOmega和ToolDelta)",
        FrameNeOmegaLauncher,
    ),
    ("§7Eulogist 框架 (赞颂者和ToolDelta并行使用)", FrameEulogistLauncher),
    ("FateArk 框架", FrameFateArk),
    ("FateArk 远程框架", FrameFateArkIndirect),
    ("NEMCTanGame 框架", FrameTanGameAccessPoint),
]

launch_args = sys_args.sys_args_to_dict()


def _strip_mc_color(text: str) -> str:
    """去掉 MC 颜色代码，用于计算终端 UI 宽度。"""
    import re
    return re.sub(r"§.", "", text)


def _display_width(text: str) -> int:
    """按中文双宽粗略计算显示宽度。"""
    width = 0
    for ch in _strip_mc_color(text):
        width += 1 if ch.isascii() else 2
    return width


def _ui_line(text: str, width: int = 68) -> str:
    """生成带边框的一行 UI 文本。"""
    pad = max(width - _display_width(text), 0)
    return f"§8║ §r{text}{' ' * pad}§8 ║§r"


def _print_ui_box(title: str, lines: list[str] | None = None, width: int = 68) -> None:
    """打印一个简洁美观的启动向导框。"""
    lines = lines or []
    fmts.print_inf("§8╔" + "═" * (width + 2) + "╗§r")
    fmts.print_inf(_ui_line(f"§b§l{title}§r", width))
    if lines:
        fmts.print_inf("§8╠" + "═" * (width + 2) + "╣§r")
        for line in lines:
            fmts.print_inf(_ui_line(line, width))
    fmts.print_inf("§8╚" + "═" * (width + 2) + "╝§r")


def _print_option(index: int, title: str, desc: str = "", badge: str = "") -> None:
    """打印统一样式的菜单选项。"""
    badge_text = f" §a[{badge}]§r" if badge else ""
    fmts.print_inf(f"§8  ┌─ §e{index}§8 ─ §f{title}{badge_text}")
    if desc:
        fmts.print_inf(f"§8  └── §7{desc}§r")


def _select_launcher_interactive(launchers: list[tuple[str, type[LAUNCHERS]]]) -> int:
    """交互选择启动器，返回 LAUNCHERS_SHOWN 中的 1 基序号。"""
    _print_ui_box(
        "选择启动器",
        [
            "§7请选择要使用的接入方式。",
            "§7选择后按原版方式填写服务器号/房间号、密码、验证服务器、fbtoken。",
        ],
    )
    for i, (launcher_name, _) in enumerate(launchers):
        _print_option(i + 1, launcher_name)
    while True:
        try:
            ch = int(input(fmts.fmt_info("请输入启动器序号: ", "§b 选择 ")).strip())
            if ch not in range(1, len(launchers) + 1):
                raise ValueError
            selected_launcher_type = launchers[ch - 1][1]
            for real_i, (_, launcher_type) in enumerate(LAUNCHERS_SHOWN, start=1):
                if launcher_type is selected_launcher_type:
                    return real_i
            raise ValueError
        except ValueError:
            fmts.print_err("输入不合法，或者是不在范围内，请重新输入。")


def _configure_github_mirror_interactive() -> str:
    """首次运行时交互配置 GitHub 镜像。"""
    _print_ui_box(
        "配置 GitHub 镜像",
        [
            "§7接入器可能需要从 GitHub 下载运行依赖。",
            "§7可以自动测速选择，也可以自行输入镜像地址。",
        ],
    )
    _print_option(1, "自动测速并选择最快镜像", "测试内置镜像列表并保存最快结果。", "推荐")
    _print_option(2, "自行输入镜像地址", "输入完整地址，例如 https://ghproxy.net。")
    while True:
        choice = input(fmts.fmt_info("请选择 1/2: ", "§b 选择 ")).strip()
        if choice == "1":
            return urlmethod.get_fastest_github_mirror()
        if choice == "2":
            mirror = input(
                fmts.fmt_info("请输入 GitHub 镜像地址: ", "§b 输入 ")
            ).strip().rstrip("/")
            if mirror.startswith(("http://", "https://")):
                return mirror
            fmts.print_err("§c镜像地址必须以 http:// 或 https:// 开头。")
            continue
        fmts.print_err("§c输入不合法，请输入 1 或 2。")


def _parse_server_number_or_code(value):
    """租赁服纯数字转 int，山头码保留字符串。"""
    if isinstance(value, int):
        return value
    value = str(value).strip()
    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def _load_original_access_point_data(launch_data: dict, launcher_type: type):
    """不使用内置验证服务时，走原版本地配置逻辑。"""
    server_key = "房间号" if launcher_type is FrameTanGameAccessPoint else "服务器号"
    serverNumber = launch_args.get("server") or launch_data.get(server_key, "")
    if serverNumber in (0, "0", "", None):
        serverNumber = input(
            fmts.fmt_info(f"请输入{server_key}/山头码: ", "§b 输入 ")
        ).strip()
    serverNumber = _parse_server_number_or_code(serverNumber)
    serverPasswd = launch_data.get("密码", "")
    if serverPasswd == "" and launcher_type is not FrameTanGameAccessPoint:
        serverPasswd = getpass.getpass(
            fmts.fmt_info("请输入服务器密码，没有则直接回车 (已隐藏):", "§6 密码 ")
        ).strip()
    elif serverPasswd == "" and launcher_type is FrameTanGameAccessPoint:
        serverPasswd = getpass.getpass(
            fmts.fmt_info("请输入房间密码，没有则直接回车 (已隐藏):", "§6 密码 ")
        ).strip()

    auth_server = launch_args.get("auth_server") or launch_data.get("验证服务器地址(更换时记得更改fbtoken)", "")
    if not auth_server:
        _print_ui_box(
            "选择验证服务器",
            [
                "§7原版逻辑需要指定验证服务器地址。",
                "§7你可以选择预设服务器，也可以输入自定义地址。",
            ],
        )
        for i, (name, url) in enumerate(tooldelta_cli.AUTH_SERVERS, start=1):
            _print_option(i, name, url)
        _print_option(len(tooldelta_cli.AUTH_SERVERS) + 1, "自定义验证服务器地址", "手动输入完整 URL。")
        while True:
            try:
                ch = int(input(fmts.fmt_info("请选择验证服务器: ", "§b 选择 ")).strip())
                if ch in range(1, len(tooldelta_cli.AUTH_SERVERS) + 1):
                    auth_server = tooldelta_cli.AUTH_SERVERS[ch - 1][1]
                    break
                if ch == len(tooldelta_cli.AUTH_SERVERS) + 1:
                    auth_server = input(fmts.fmt_info("请输入验证服务器地址: ", "§b 输入 ")).strip()
                    if auth_server:
                        break
                raise ValueError
            except ValueError:
                fmts.print_err("输入不合法，或者是不在范围内，请重新输入。")

    fbtoken = launch_args.get("T") or sys_args.sys_args_to_dict().get("user-token")
    if not fbtoken:
        if_token()
        fbtokenFix()
        with open("fbtoken", encoding="utf-8") as f:
            fbtoken = f.read().strip()
    else:
        if_token(fbtoken)
        fbtokenFix(fbtoken)

    launch_data[server_key] = serverNumber
    launch_data["密码"] = serverPasswd
    launch_data["验证服务器地址(更换时记得更改fbtoken)"] = auth_server
    return serverNumber, serverPasswd, fbtoken, auth_server


class ConfigLoader:
    def __init__(self, frame: "ToolDelta"):
        self.frame = frame

    def load_tooldelta_cfg_and_get_launcher(self) -> LAUNCHERS:
        """加载配置文件"""
        cfg.write_default_cfg_file("ToolDelta基本配置.json", tooldelta_cfg.LAUNCH_CFG)
        try:
            # 读取配置文件
            cfgs = cfg.get_cfg("ToolDelta基本配置.json", tooldelta_cfg.LAUNCH_CFG_STD)
            self.launchMode = int(launch_args.get("launchMode") or "0") or cfgs["启动器启动模式(请不要手动更改此项, 改为0可重置)"]
            self.plugin_market_url = cfgs["插件市场源"]
            fmts.logger.switch_logger(cfgs["是否记录日志"])
            if self.launchMode != 0 and self.launchMode not in range(
                1, len(LAUNCHERS_SHOWN) + 1
            ):
                raise cfg.ConfigError("你不该随意修改启动器模式，现在赶紧把它改回 0 吧")
        except cfg.ConfigError as err:
            # 配置文件有误
            r = self.upgrade_cfg()
            if r:
                fmts.print_war("配置文件未升级，已自动升级，请重启 ToolDelta")
            else:
                fmts.print_err(f"ToolDelta 基本配置有误，需要更正：{err}")
            raise SystemExit from err
        # 每个启动器框架的单独启动配置之前
        if self.launchMode == 0:
            ch = _select_launcher_interactive(LAUNCHERS_SHOWN)
            cfgs["启动器启动模式(请不要手动更改此项, 改为0可重置)"] = ch
            cfg.write_default_cfg_file("ToolDelta基本配置.json", cfgs, True)
        section: int = cfgs["启动器启动模式(请不要手动更改此项, 改为0可重置)"]
        launcher = LAUNCHERS_SHOWN[section - 1][1]()
        launcher_type = type(launcher)
        # 首次配置 GitHub 镜像：自动测速选择最快镜像。
        github_mirror = cfgs["全局GitHub镜像"].strip()
        if not github_mirror:
            github_mirror = _configure_github_mirror_interactive()
            cfgs["全局GitHub镜像"] = github_mirror
            cfg.write_default_cfg_file("ToolDelta基本配置.json", cfgs, True)
        urlmethod.set_global_github_src_url(github_mirror)
        # 每个启动器框架的单独启动配置
        LAUNCHER_CONFIG_KEY = ""
        # 这是 普通 NeOmega 接入点
        if launcher_type is FrameNeOmgAccessPoint:
            launch_data = cfgs.get(
                "NeOmega接入点启动模式", tooldelta_cfg.LAUNCHER_NEOMEGA_DEFAULT
            )
            LAUNCHER_CONFIG_KEY = "NeOmega接入点启动模式"
            try:
                cfg.check_auto(tooldelta_cfg.LAUNCHER_NEOMEGA_STD, launch_data)
            except cfg.ConfigError as err:
                r = self.upgrade_cfg()
                if r:
                    fmts.print_war("配置文件未升级，已自动升级，请重启 ToolDelta")
                else:
                    fmts.print_err(
                        f"ToolDelta 基本配置-NeOmega 启动配置有误，需要更正：{err}"
                    )
                raise SystemExit from err
        # 这是 NeOmega 和 ToolDelta 并行启动
        elif launcher_type is FrameNeOmegaLauncher:
            LAUNCHER_CONFIG_KEY = "NeOmega并行ToolDelta启动模式"
            launch_data = cfgs.get(
                LAUNCHER_CONFIG_KEY,
                tooldelta_cfg.LAUNCHER_NEOMG2TD_DEFAULT,
            )
            try:
                cfg.check_auto(tooldelta_cfg.LAUNCHER_NEOMG2TD_STD, launch_data)
            except cfg.ConfigError as err:
                r = self.upgrade_cfg()
                if r:
                    fmts.print_war("配置文件未升级，已自动升级，请重启 ToolDelta")
                else:
                    fmts.print_err(
                        f"ToolDelta 基本配置-NeOmega 启动配置有误，需要更正：{err}"
                    )
                raise SystemExit from err
        elif launcher_type is FrameNeOmgAccessPointRemote:
            LAUNCHER_CONFIG_KEY = "NeOmega远程接入点模式"
            launch_data = cfgs.get(
                LAUNCHER_CONFIG_KEY, tooldelta_cfg.LAUNCHER_NEOMEGARM_DEFAULT
            )
            cfgs[LAUNCHER_CONFIG_KEY] = launch_data
            cfg.write_default_cfg_file("ToolDelta基本配置.json", cfgs, True)
            try:
                cfg.check_auto(tooldelta_cfg.LAUNCHER_NEOMEGARM_STD, launch_data)
            except cfg.ConfigError as err:
                r = self.upgrade_cfg()
                if r:
                    fmts.print_war("配置文件未升级，已自动升级，请重启 ToolDelta")
                else:
                    fmts.print_err(
                        f"ToolDelta 基本配置-远程NeOmega 启动配置有误，需要更正：{err}"
                    )
        elif launcher_type is FrameEulogistLauncher:
            # 不需要任何配置文件
            ...
        elif launcher_type is FrameFateArk:
            LAUNCHER_CONFIG_KEY = "FateArk接入点启动模式"
            launch_data = cfgs.get(
                LAUNCHER_CONFIG_KEY, tooldelta_cfg.LAUNCHER_FATEARK_DEFAULT
            )
            try:
                cfg.check_auto(tooldelta_cfg.LAUNCHER_FATEARK_STD, launch_data)
            except cfg.ConfigError as err:
                r = self.upgrade_cfg()
                if r:
                    fmts.print_war("配置文件未升级，已自动升级，请重启 ToolDelta")
                else:
                    fmts.print_err(
                        f"ToolDelta 基本配置-FateArk 启动配置有误，需要更正：{err}"
                    )
                raise SystemExit from err
        elif launcher_type is FrameFateArkIndirect:
            LAUNCHER_CONFIG_KEY = "FateArk远程接入点启动模式"
            launch_data = cfgs.get(
                LAUNCHER_CONFIG_KEY, tooldelta_cfg.LAUNCHER_FATEARK_INDIRECT_DEFAULT
            )
            try:
                cfg.check_auto(tooldelta_cfg.LAUNCHER_FATEARK_INDIRECT_STD, launch_data)
            except cfg.ConfigError as err:
                r = self.upgrade_cfg()
                if r:
                    fmts.print_war("配置文件未升级，已自动升级，请重启 ToolDelta")
                else:
                    fmts.print_err(
                        f"ToolDelta 基本配置-FateArk 启动配置有误，需要更正：{err}"
                    )
                raise SystemExit from err
        elif launcher_type is FrameTanGameAccessPoint:
            LAUNCHER_CONFIG_KEY = "NEMCTanGame接入点启动模式"
            launch_data = cfgs.get(
                LAUNCHER_CONFIG_KEY, tooldelta_cfg.LAUNCHER_NEMCTANGAME_DEFAULT
            )
            try:
                cfg.check_auto(tooldelta_cfg.LAUNCHER_NEMCTANGAME_STD, launch_data)
            except cfg.ConfigError as err:
                r = self.upgrade_cfg()
                if r:
                    fmts.print_war("配置文件未升级，已自动升级，请重启 ToolDelta")
                else:
                    fmts.print_err(
                        f"ToolDelta 基本配置-NEMCTanGame 启动配置有误，需要更正：{err}"
                    )
                raise SystemExit from err
        else:
            raise ValueError(f"LAUNCHER error: {launcher_type.__name__}")

        if launcher_type in ACCESS_POINT_LAUNCHERS:
            serverNumber, serverPasswd, fbtoken, auth_server = _load_original_access_point_data(
                launch_data, launcher_type
            )
            cfgs[LAUNCHER_CONFIG_KEY] = launch_data
            cfg.write_default_cfg_file("ToolDelta基本配置.json", cfgs, True)
            launcher.set_launch_data(
                serverNumber, serverPasswd, fbtoken, auth_server
            )

        fmts.print_suc("配置文件读取完成")
        return launcher

    @staticmethod
    def upgrade_cfg() -> bool:
        """升级配置文件

        Returns:
            bool: 是否升级了配置文件
        """
        old_cfg: dict = cfg.get_cfg("ToolDelta基本配置.json", {})
        old_cfg_keys = old_cfg.keys()
        need_upgrade_cfg = False
        for k, v in tooldelta_cfg.LAUNCH_CFG.items():
            if k not in old_cfg_keys:
                old_cfg[k] = v
                need_upgrade_cfg = True
        if need_upgrade_cfg:
            cfg.write_default_cfg_file("ToolDelta基本配置.json", old_cfg, True)
        return need_upgrade_cfg

    @staticmethod
    def change_config():
        """修改配置文件"""
        try:
            old_cfg = cfg.get_cfg(
                "ToolDelta基本配置.json", tooldelta_cfg.LAUNCH_CFG_STD
            )
        except FileNotFoundError:
            fmts.clean_print("§c未初始化配置文件, 无法进行修改")
            return
        except cfg.ConfigError as err:
            fmts.print_err(f"配置文件损坏：{err}")
            return
        if (
            old_cfg["启动器启动模式(请不要手动更改此项, 改为0可重置)"] - 1
        ) not in range(0, len(LAUNCHERS_SHOWN)):
            fmts.print_err(
                f"配置文件损坏：启动模式错误：{old_cfg['启动器启动模式(请不要手动更改此项, 改为0可重置)']}"
            )
            return
        while 1:
            md = tuple(name.replace("§7", "") for name, _ in LAUNCHERS_SHOWN)
            fmts.clean_print("§b现有配置项如下:")
            fmts.clean_print(
                f" 1. 启动器启动模式：{md[old_cfg['启动器启动模式(请不要手动更改此项, 改为0可重置)'] - 1]}"
            )
            fmts.clean_print(f" 2. 是否记录日志：{old_cfg['是否记录日志']}")
            fmts.clean_print("    §a直接回车: 保存并退出")
            resp = input(fmts.clean_fmt("§6输入序号可修改配置项(0~4): ")).strip()
            if resp == "":
                cfg.write_default_cfg_file("ToolDelta基本配置.json", old_cfg, True)
                fmts.clean_print("§a配置已保存!")
                return
            match resp:
                case "1":
                    fmts.print_inf(
                        "选择启动器启动模式 (之后可在 ToolDelta 启动配置更改):"
                    )
                    for i, (launcher_name, _) in enumerate(LAUNCHERS_SHOWN):
                        fmts.print_inf(f" {i + 1} - {launcher_name}")
                    while 1:
                        try:
                            ch = int(input(fmts.clean_fmt("请选择：")))
                            if ch not in range(1, len(LAUNCHERS_SHOWN) + 1):
                                raise ValueError
                            old_cfg[
                                "启动器启动模式(请不要手动更改此项, 改为0可重置)"
                            ] = ch
                            break
                        except ValueError:
                            fmts.print_err("输入不合法，或者是不在范围内，请重新输入")
                            continue
                    input(
                        fmts.clean_fmt(
                            f"§a已选择启动器启动模式：§f{md[old_cfg['启动器启动模式(请不要手动更改此项, 改为0可重置)'] - 1]}, 回车键继续"
                        )
                    )
                case "2":
                    old_cfg["是否记录日志"] = [True, False][old_cfg["是否记录日志"]]
                    input(
                        fmts.clean_fmt(
                            f"日志记录模式已改为：{['§c关闭', '§a开启'][old_cfg['是否记录日志']]}, 回车键继续"
                        )
                    )
