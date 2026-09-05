# ToolDelta 接入点适配 — Maindev39 v860

## 概述

在 ToolDelta 启动器中增加了 **3.8 / 3.9 版本选择**，用户可在首次启动时自由选择：

| 选项 | 版本 | 接入点 | 验证服务 |
|------|------|--------|----------|
| **1** | 3.8 | FateArk (gRPC) | 3.8 ShenAuth / 在线 fbToken |
| **2** | 3.9 | Maindev39 (HTTP) | 3.9 ShenAuth / 内置 Cookie |

## 文件结构

```
sy-tooldetla-master/
├── maindev39_files/                    # 3.9 接入点文件（首次启动时自动复制到 bin）
│   ├── maindev.exe                     # 协议 860 接入点
│   └── shenauth_win.exe                # 3.9 验证服务
├── tooldelta/
│   ├── constants/
│   │   ├── tooldelta_cfg.py            ← 新增 MAINDEV39 配置模板
│   │   └── tooldelta_cli.py            （未改动）
│   └── internal/
│       ├── config_loader.py            ← 新增 3.8/3.9 选择逻辑
│       └── launch_cli/
│           ├── __init__.py             ← 注册 FrameMaindev39
│           ├── maindev39_access_point.py ← 新增：Maindev39 启动器
│           └── fateark_access_point.py   （3.8 原有，未改动）
```

## 使用方式

### 首次启动

1. 运行 ToolDelta，选择版本：
   ```
   请选择你的网易租赁服大版本：
    1 - 3.8 (使用 FateArk 接入点)
    2 - 3.9 (使用 Maindev39 接入点 [新])
   请选择 (1/2):
   ```
2. 选 **2** → 进入 3.9 模式
3. 输入服务器密钥（或跳过用内置号）
4. 输入 3.9 内置 Cookie（compact JSON 格式）

### 3.9 Cookie 格式

在 `ToolDelta基本配置.json` 的 `Maindev39接入点启动模式` 中：
```json
{
    "Maindev39接入点启动模式": {
        "服务器号": 34465851,
        "密码": "123126",
        "验证服务器地址": "http://127.0.0.1:25566",
        "内置Cookie": "{\"sauth_json\":\"...\"}"
    }
}
```

- `验证服务器地址` — ShenAuth 地址，默认 `http://127.0.0.1:25566`
- `内置Cookie` — 紧凑 JSON 格式的 cookie，直接注入 `FUNAUTH_FIXED_COOKIE`

### 切换版本

- 编辑 `ToolDelta基本配置.json`，将 `启动器启动模式` 改为 `0` 可重新选择
- 模式 5 = 3.8 FateArk
- 模式 8 = 3.9 Maindev39

### 手动替换接入点文件

```powershell
# 把新编译的 maindev.exe 放到 maindev39_files/
copy maindev.exe sy-tooldetla-master\maindev39_files\

# 同样替换 shenauth
copy shenauth_win.exe sy-tooldetla-master\maindev39_files\
```

下次启动时 ToolDelta 会自动复制到 `tooldelta/bin/`。

## 3.9 HTTP API

Maindev39 在 `http://127.0.0.1:9999` 提供：

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/` | 健康检查 → `Still Alive` |
| GET | `/online` | 在线人数（WS 身份 /list，不刷屏） |
| POST | `/place_nbt_block` | 放置 NBT 方块 |
| GET | `/process_exit` | 安全退出 |

## 已知限制

- 命令通过 HTTP 代理，`waitForResp=True` 暂不支持（3.9 Sizukana API 不同步返回 CommandOutput）
- sendPacket 通道待完善（需要 maindev 暴露包转发接口）
- 启动参数默认 `-ccx=10000 -ccy=64 -ccz=10000`，可在 maindev39_access_point.py 修改

## 维护

要更新接入点版本：
1. 编译新的 maindev.exe → 放到 `maindev39_files/`
2. 3.9 shenauth 更新 → 放到 `maindev39_files/`
3. ToolDelta 启动时自动检测并复制
