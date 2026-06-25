"""
Global GPU Semaphore — 跨會議的 GPU 併發控制 + 階梯觸發。

解決問題：多場會議同時觸發時，各自的 ASR_PARALLELISM=15 導致
90 requests 湧入 GPU (capacity=30)，造成大量 429 retry 浪費。

方案：
1. 進程級 threading.Semaphore 限制全局 GPU 併發 ≤ capacity×0.8
2. per-meeting 限制防止單場獨佔
3. 階梯觸發 (stagger)：每場會議開始 GPU 處理前間隔 30s，
   讓 GPU autoscaler 漸進升溫，避免 cold start 集中 429

技術選型：
- 使用 threading.Semaphore（非 asyncio.Semaphore）
  因為 FastAPI BackgroundTasks 每個 task 用 asyncio.run() 建立獨立 event loop，
  asyncio.Semaphore 無法跨 thread/event loop 共享。
- 在 async code 中透過 asyncio.to_thread() 包裝 acquire，避免 block event loop。
"""

import asyncio
import os
import threading
from collections import deque
from time import time, sleep
from typing import Optional

import logging

logger = logging.getLogger(__name__)

# 全局 GPU 併發上限 = GPU maxScale × concurrency × 0.8
# 15 instances × 2 concurrency = 30 → 30 × 0.83 ≈ 25
GPU_GLOBAL_CONCURRENCY = int(os.getenv("GPU_GLOBAL_CONCURRENCY", "25"))

# 單場會議最多佔幾個 GPU slot（防止大會議餓死小會議）
# 2.3hr = 10 chunks，設 10 讓其全速；4.3hr = 18 chunks 被限制
GPU_PER_MEETING_MAX = int(os.getenv("GPU_PER_MEETING_MAX", "10"))

# 階梯觸發間隔（秒）：每場會議開始 GPU 處理前的最小間隔
# T6 驗證 30s 間隔 4 場全部成功，零 429 失敗
GPU_STAGGER_INTERVAL = int(os.getenv("GPU_STAGGER_INTERVAL", "30"))


class GPUQueueStats:
    """Thread-safe 統計追蹤"""

    def __init__(self):
        self._lock = threading.Lock()
        self.total_acquired = 0
        self.total_released = 0
        self.total_queued = 0  # waited > 0.5s
        self.peak_concurrent = 0
        self.current_concurrent = 0
        self.queue_wait_times: deque = deque(maxlen=200)
        self.stagger_waits: int = 0  # 因 stagger 而等待的會議數

    def on_acquire(self, wait_time: float):
        with self._lock:
            self.total_acquired += 1
            self.current_concurrent += 1
            if self.current_concurrent > self.peak_concurrent:
                self.peak_concurrent = self.current_concurrent
            if wait_time > 0.5:
                self.total_queued += 1
                self.queue_wait_times.append(wait_time)

    def on_release(self):
        with self._lock:
            self.total_released += 1
            self.current_concurrent -= 1

    def on_stagger(self):
        with self._lock:
            self.stagger_waits += 1

    def snapshot(self) -> dict:
        with self._lock:
            avg_wait = (
                sum(self.queue_wait_times) / len(self.queue_wait_times)
                if self.queue_wait_times
                else 0.0
            )
            max_wait = max(self.queue_wait_times) if self.queue_wait_times else 0.0
            return {
                "current_concurrent": self.current_concurrent,
                "peak_concurrent": self.peak_concurrent,
                "total_processed": self.total_acquired,
                "total_queued": self.total_queued,
                "avg_queue_wait_sec": round(avg_wait, 1),
                "max_queue_wait_sec": round(max_wait, 1),
                "stagger_waits": self.stagger_waits,
                "stagger_interval_sec": GPU_STAGGER_INTERVAL,
                "capacity": GPU_GLOBAL_CONCURRENCY,
                "per_meeting_max": GPU_PER_MEETING_MAX,
            }


# --- Module-level singletons (process-wide) ---

_global_sem = threading.Semaphore(GPU_GLOBAL_CONCURRENCY)
_meeting_sems: dict[str, threading.Semaphore] = {}
_meeting_sems_lock = threading.Lock()
_stats = GPUQueueStats()

# 階梯觸發控制
_stagger_lock = threading.Lock()
_last_meeting_start: float = 0.0  # 上一場會議開始 GPU 處理的 timestamp


def _get_meeting_sem(meeting_id: str) -> threading.Semaphore:
    with _meeting_sems_lock:
        if meeting_id not in _meeting_sems:
            _meeting_sems[meeting_id] = threading.Semaphore(GPU_PER_MEETING_MAX)
        return _meeting_sems[meeting_id]


def stagger_wait(meeting_id: str) -> float:
    """
    階梯觸發閘門：確保每場會議開始 GPU 處理前間隔至少 GPU_STAGGER_INTERVAL 秒。
    
    效果：6 場同時觸發 → 實際 GPU 開始時間為 0s, 30s, 60s, 90s, 120s, 150s
    讓 GPU autoscaler 有時間漸進啟動 instances，避免集中 cold start 429。
    
    Returns: actual wait time in seconds (0 if no wait needed)
    """
    global _last_meeting_start
    
    if GPU_STAGGER_INTERVAL <= 0:
        return 0.0

    with _stagger_lock:
        now = time()
        elapsed = now - _last_meeting_start
        if elapsed < GPU_STAGGER_INTERVAL:
            wait_needed = GPU_STAGGER_INTERVAL - elapsed
        else:
            wait_needed = 0.0
        # 預約這個 slot 的開始時間
        _last_meeting_start = now + wait_needed

    if wait_needed > 0:
        logger.info(
            f"[GPUStagger] {meeting_id[:8]} waiting {wait_needed:.1f}s "
            f"(stagger interval={GPU_STAGGER_INTERVAL}s)"
        )
        _stats.on_stagger()
        sleep(wait_needed)
        return wait_needed
    
    return 0.0


def acquire_gpu_slot(meeting_id: str, timeout: float = 1800.0) -> float:
    """
    取得一個 GPU slot（blocking with timeout）。
    先取 per-meeting semaphore，再取 global semaphore。
    Returns: wait_time in seconds.
    Raises: TimeoutError if slot not acquired within timeout.
    """
    start = time()
    if not _get_meeting_sem(meeting_id).acquire(timeout=timeout):
        raise TimeoutError(
            f"GPU slot acquire timeout ({timeout}s) waiting for per-meeting semaphore"
        )
    remaining = timeout - (time() - start)
    if remaining <= 0 or not _global_sem.acquire(timeout=max(remaining, 1.0)):
        _get_meeting_sem(meeting_id).release()
        raise TimeoutError(
            f"GPU slot acquire timeout ({timeout}s) waiting for global semaphore"
        )
    wait_time = time() - start
    _stats.on_acquire(wait_time)
    return wait_time


def release_gpu_slot(meeting_id: str):
    """歸還一個 GPU slot。"""
    _global_sem.release()
    _get_meeting_sem(meeting_id).release()
    _stats.on_release()


def cleanup_meeting(meeting_id: str):
    """會議處理完畢，清除 per-meeting semaphore 避免記憶體洩漏。"""
    with _meeting_sems_lock:
        _meeting_sems.pop(meeting_id, None)


async def acquire_gpu_slot_async(meeting_id: str) -> float:
    """
    Non-blocking async wrapper — 在 event loop 中排隊而不阻塞其他 coroutines。
    使用 asyncio.to_thread 將 blocking acquire 放到 thread pool。
    """
    return await asyncio.to_thread(acquire_gpu_slot, meeting_id)


def get_stats() -> dict:
    """取得 GPU queue 即時統計。"""
    return _stats.snapshot()


def reset_stats():
    """重置統計（用於測試）。"""
    global _stats, _last_meeting_start
    _stats = GPUQueueStats()
    _last_meeting_start = 0.0


# Log config on import
logger.info(
    f"[GPUSemaphore] initialized: global_concurrency={GPU_GLOBAL_CONCURRENCY}, "
    f"per_meeting_max={GPU_PER_MEETING_MAX}, stagger_interval={GPU_STAGGER_INTERVAL}s"
)
