import os

from . import fmts

def if_token(fbtoken: str | None = None) -> None:
    """检查路径下是否有 fbtoken，没有就提示输入
    如果传入了 fbtoken 参数，则跳过文件检查（内置 Cookie 模式）

    Raises:
        SystemExit: 未输入 fbtoken
    """
    if fbtoken is not None:
        # 内置 Cookie 模式，不需要读取文件
        return
    if not os.path.isfile("fbtoken"):
        fmts.print_inf(
            "请到对应的验证服务器官网下载 FBToken，并放在本目录中，或者在下面输入 fbtoken"
        )
        fbtoken = input(fmts.fmt_info("请输入 fbtoken: ", "§b 输入 "))
        if fbtoken:
            with open("fbtoken", "w", encoding="utf-8") as f:
                f.write(fbtoken)
        else:
            fmts.print_err("未输入 fbtoken, 无法继续")
            raise SystemExit


def fbtokenFix(fbtoken: str | None = None) -> None:
    """修复 fbtoken 里的换行符
    如果传入了 fbtoken 参数，仅做换行符清理，不操作文件
    """
    if fbtoken is not None:
        # 内置 Cookie 模式，只清理换行符，不操作文件
        if "\n" in fbtoken:
            fmts.print_war("fbtoken 里有换行符，会造成 fb 登录失败，已自动修复")
        return
    with open("fbtoken", encoding="utf-8") as file:
        token = file.read()
        if "\n" in token:
            fmts.print_war("fbtoken 里有换行符，会造成 fb 登录失败，已自动修复")
            with open("fbtoken", "w", encoding="utf-8") as file2:
                file2.write(token.replace("\n", ""))
