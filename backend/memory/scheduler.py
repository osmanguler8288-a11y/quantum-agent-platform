"""
MemoryScheduler — 后台定时任务，每天清理一次低重要性记忆

启动方式：在 app 启动时调用 start_memory_scheduler()
"""

import threading
import time
from typing import Optional, Callable

from memory.manager import MemoryManager


class MemoryScheduler:
    """后台定时清理低重要性记忆"""

    def __init__(
        self,
        llm,
        interval_seconds: int = 86400,    # 默认 1 天
        forget_threshold: float = 0.2,
        max_age_days: int = 30,
        user_iter: Optional[Callable] = None,
    ):
        self.llm = llm
        self.interval = interval_seconds
        self.forget_threshold = forget_threshold
        self.max_age_days = max_age_days
        self.user_iter = user_iter      # 返回所有 user_id 列表的函数
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ─── 启动 / 停止 ────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="memory-scheduler")
        self._thread.start()
        print(f"[memory-scheduler] 启动，每 {self.interval}s 跑一次清理")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    # ─── 主循环 ────────────────────────────────────
    def _loop(self):
        # 启动后等 60s 再跑第一次（让服务先稳定）
        if self._stop.wait(60):
            return

        while not self._stop.is_set():
            try:
                self._run_once()
            except Exception as e:
                print(f"[memory-scheduler] 清理出错: {e}")

            # 等待下一次（可被 stop 中断）
            if self._stop.wait(self.interval):
                break

        print("[memory-scheduler] 已停止")

    # ─── 单次执行 ──────────────────────────────────
    def _run_once(self):
        user_ids = self._get_all_users()
        if not user_ids:
            print("[memory-scheduler] 无用户需清理")
            return

        total_forgotten = 0
        for user_id in user_ids:
            try:
                mgr = MemoryManager(user_id=str(user_id), llm=self.llm,
                                    enable_working=False, enable_perceptual=False)
                if not mgr.store.available:
                    continue
                count = mgr.forget_memories(
                    strategy="combined",
                    threshold=self.forget_threshold,
                    max_age_days=self.max_age_days,
                )
                if count > 0:
                    print(f"[memory-scheduler] 用户 {user_id}: 清理 {count} 条")
                total_forgotten += count
            except Exception as e:
                print(f"[memory-scheduler] 用户 {user_id} 清理失败: {e}")

        print(f"[memory-scheduler] 本次清理完成：共遗忘 {total_forgotten} 条记忆")

    # ─── 获取所有用户 ID ────────────────────────────
    def _get_all_users(self) -> list[str]:
        """从 Milvus 查询所有不同的 user_id"""
        if self.user_iter:
            try:
                return self.user_iter()
            except Exception:
                return []

        # 默认实现：直接查 Milvus
        try:
            from memory.store import MilvusStore
            from memory.models import MemoryConfig
            store = MilvusStore(MemoryConfig())
            if not store.available:
                return []
            # 查询所有记忆的 user_id 字段（不去重）
            results = store.client.query(
                collection_name=store.config.milvus_collection,
                filter='user_id != ""',
                output_fields=["user_id"],
                limit=10000,
            )
            user_ids = list({r.get("user_id") for r in results if r.get("user_id")})
            print(f"[memory-scheduler] 发现 {len(user_ids)} 个用户")
            return user_ids
        except Exception as e:
            print(f"[memory-scheduler] 获取用户列表失败: {e}")
            return []


# ─── 全局单例 ────────────────────────────────────
_scheduler: Optional[MemoryScheduler] = None


def start_memory_scheduler(llm, interval_seconds: int = 86400):
    """启动后台记忆清理任务（默认 1 天跑一次）"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = MemoryScheduler(llm=llm, interval_seconds=interval_seconds)
    _scheduler.start()
    return _scheduler


def stop_memory_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
