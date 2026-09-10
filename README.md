<h1 align="center">神翼面板 · sy-tooldetla</h1>

<p align="center">
  <img src="https://img.shields.io/badge/基于-ToolDelta-blue" alt="Based on ToolDelta">
  <img src="https://img.shields.io/badge/Python-3.10%2B-green" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/License-BSD--3--Clause-orange" alt="License">
</p>

**神翼面板**是基于 [ToolDelta](https://github.com/ToolDelta/ToolDelta) 的 Web 管理面板：把原本不支持插件 / 模组的**网易租赁服、山头服**接进来，通过进服的机器人托管插件能力，再用浏览器完成日常管理。它解决的是机器人账号共享带来的连服不稳问题，同时为手机端租赁服提供更稳定的机器人插件加载体验。

```
你的租赁服（原版，不支持插件）
        ↑  机器人进服托管
神翼面板（本仓库：ToolDelta 定制版 + Web 面板）
        ↑  http://127.0.0.1:5101
服主浏览器（看状态 / 发命令 / 管玩家 / 装插件）
```

---

## 特性

- **Web 面板即开即用**：第一次启动自动生成独立访问账号，浏览器登录后即可管理，无需命令行。
- **多种服务器接入**：租赁服、山头服；支持 NeOmega / FateArk / Eulogist / TanGame 等启动器，按原版方式填入服务器号 / 密码 / 验证服务器即可。
- **原版 ToolDelta 全功能保留**：插件加载器、插件市场、整合包等均可用。
- **移动端友好**：手机浏览器自动切换底部导航与抽屉式操作，管理服务器不用开电脑。
- **安全与追溯**：管理员权限可视化编辑（含离线）、玩家动态与历史名册（改名可追溯）、内置黑名单（按名字 + XUID 双匹配）、可开关的进服审核。
- **商用部署支持**：内置多租户网关接入协议（环境变量注入实例标识），可对接自有面板系统批量开实例。

---

## 快速开始

### 方式一：本机运行

需要 Python 3.10+（3.12 实测通过）。

```bash
# 1. 安装依赖（推荐虚拟环境）
pip install -e .

# 2. 启动面板
python web_run.py --host 127.0.0.1 --port 5101
```

启动后终端会打印**访问地址 / 登录入口 / 账号 / 密码**，凭据保存在运行目录的 `web_panel_data/credentials.json`：

```
========================================
神翼面板已启动

访问地址：http://127.0.0.1:5101
登录入口：http://127.0.0.1:5101/login
实例编号：a-xxxxxxxx
账号：admin_xxxxxx
密码：xxx-xxx-xxx
========================================
```

浏览器打开登录入口，用打印的账号密码进入面板。

### 方式二：Docker

```bash
docker build -t shenyi-panel .
# 挂载数据目录，凭据与配置持久化保存
docker run -d -p 5101:5101 -v "$PWD/data:/data" --name shenyi-panel shenyi-panel
```

容器内面板监听 `5101`，数据（登录凭据、启动配置、插件）保存在 `/data`（通过环境变量 `SHENYI_CREDENTIALS_FILE=/data/.shenyi-panel/credentials.json` 及入口脚本软链实现），重建容器不丢失。

---

## 首次使用（三步）

面板内的新手引导会带你完成：

1. **填写启动配置**：到「设置」页选择接入方式（NeOmega / FateArk / TanGame 等）并按原版方式填入服务器号、密码、验证服务器地址，一次填好永久生效。
2. **启动服务**：回「控制台」点「启动服务」，机器人会自动连上你的服务器。
3. **安装插件**：去「市场」给服务器添加原本没有的功能。

> 未完成配置时点「启动」会被拦截并引导到配置页，不会在后台卡死。

---

## 界面模块

| 页面 | 作用 |
|---|---|
| 控制台 | 机器人运行状态、启停、快捷入口、**在线人数曲线**、运行日志 |
| 消息 | 与服务器对话：发公告、聊天、执行命令，回应实时回流；支持**聊天记录检索** |
| 玩家 | 在线玩家列表、详情（能力 / 背包 / 坐标）、踢出 / 给物品 / 传送 / 封禁、**玩家动态**、**历史玩家名册**、**内置黑名单**、**进服审核** |
| 服务器 | 时间、天气、难度、游戏规则一键调整，常用命令与操作记录，**权限管理** |
| 插件 | 已安装插件的启用 / 停用 / 配置 / 删除 |
| 市场 | 插件与整合包商店，含前置依赖，一键下载安装 |
| 设置 | 启动配置与文件管理（插件文件、配置、数据、日志） |

> 登录页与控制台等核心页面已做手机端适配；浏览器端操作建议使用最新版 Chrome / Edge。

---

## 配置说明

- 插件市场源、GitHub 镜像、日志开关均可在「设置 → 启动配置」中修改（GitHub 镜像留空时启动会按原版流程自动测速选择）。
- fbtoken 按原版方式使用：把验证服务器提供的 fbtoken 文件放在运行目录，或在「设置」页直接填写保存。
- 原版 CLI 入口 `main.py` 仍然可用，与 Web 面板互不冲突。

---

## 目录结构

```
web_panel/                 Web 面板（Flask + WebSocket）
  app.py                   应用与路由、登录守卫
  bridge.py                框架管理器（后台线程跑 ToolDelta）
  auth_service.py          独立访问账号 / 凭据生成
  config_service.py        启动配置读写
  plugin_service.py        插件管理 / 市场 / 整合包
  file_service.py          文件管理（白名单虚拟根目录）
  static/                  前端（index.html / app.js / style.css）
web_run.py                 Web 入口
deploy/docker/             Docker 入口脚本
tooldelta/                 ToolDelta 定制版框架
main.py                    CLI 入口（原版菜单）
```

---

## 常见问题

- **忘记面板登录密码**：删除运行目录下 `web_panel_data/credentials.json` 后重启，会生成新账号密码。
- **启动后机器人没进服**：到「设置」检查启动配置是否完整；控制台日志会显示连服进度。
- **面板端口被占用**：`python web_run.py --port 其他端口`。

---

## 致谢与开源协议

- 本仓库为 [ToolDelta](https://github.com/ToolDelta/ToolDelta) 的二改发行版，遵循 **BSD 3-Clause License**，详见 [LICENSE](LICENSE)。
- 感谢 ToolDelta 及插件生态的开发者们。
- 神翼面板（`web_panel/` 及本仓库新增内容）版权归神之翼工作室所有，以 BSD 3-Clause 开源；
  **开源免费仅限个人学习与非商业用途，任何商业使用（销售、收费部署/托管、以本软件为基础提供收费服务等）
  须事先获得作者授权**，详见 [LICENSE](LICENSE) 第 4 条。
- 商用授权两种模式（详见 [LICENSE](LICENSE) 第 4 条），请联系作者：**QQ 1955306516**（神之翼工作室）：
  1. **贡献式授权**：以共同维护者身份持续参与开发，每月至少提交一次被正式合并的 PR
     或同等维护记录，即可获得当月商业授权；
  2. **付费授权**：99 元/月购买商业授权。
