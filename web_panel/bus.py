"""事件总线 + 日志桥接。

所有 fmts.print_* 输出最终走 Python logging（见 tooldelta/utils/fmts）。
本模块注册一个 logging.Handler，把每条日志广播给所有 WebSocket 订阅者，
并保留环形历史供新连接回放。
"""
import logging
import queue
import threading
import time
from collections import deque

HISTORY_LIMIT = 800
QUEUE_LIMIT = 2000


class MessageBus:
    """线程安全的消息总线（日志 / 聊天 / 状态事件）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: list["queue.Queue"] = []
        self._history: deque = deque(maxlen=HISTORY_LIMIT)

    def subscribe(self) -> "queue.Queue":
        q = queue.Queue(maxsize=QUEUE_LIMIT)
        with self._lock:
            self._subscribers.append(q)
            for item in self._history:
                q.put_nowait(item)
        return q

    def unsubscribe(self, q: "queue.Queue") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, item: dict) -> None:
        with self._lock:
            self._history.append(item)
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(item)
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(item)
                except queue.Full:
                    pass


class BusLogHandler(logging.Handler):
    """把 logging record 转成总线事件。消息保留原始 § 颜色码，由前端解析。"""

    def __init__(self, bus: MessageBus):
        super().__init__()
        self.bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bus.publish(
                {
                    "type": "log",
                    "level": record.levelname,
                    "msg": record.getMessage(),
                    "ts": time.time(),
                }
            )
        except Exception:
            pass


bus = MessageBus()
_handler = BusLogHandler(bus)
_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_handler)
