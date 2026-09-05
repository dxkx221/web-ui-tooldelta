"""ToolDelta Web 面板 — 桥接层包。

将阻塞式 CLI 框架包在后台线程中，通过 Flask + WebSocket 暴露为 Web 卡片式控制面板。
底层框架逻辑不做任何改动，仅在入口加 Web 模式分支。
"""
