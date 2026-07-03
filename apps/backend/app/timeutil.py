"""
時間序列化工具（2026-07-03）。

問題根因：資料庫以「naive UTC」（`datetime.utcnow()`）儲存時間，API 若直接序列化
會輸出不含時區後綴的字串（例：`2026-07-03T02:04:09.439516`）。前端 `new Date()`
會將此字串當成「瀏覽器本地時間」解析，導致即使指定 `timeZone: 'Asia/Taipei'`
也無法正確換算，畫面顯示的其實是原始 UTC 時鐘值而非台北時間。

修正原則：**API 邊界一律輸出 UTC-aware ISO8601（帶 `Z`）**。前端拿到帶時區的
字串後，`new Date()` 會解析成正確的「瞬間」，再以 `timeZone: 'Asia/Taipei'`
格式化即為正確的台北時間（UTC+8）。

- naive datetime → 視為 UTC（符合本專案儲存慣例）
- aware datetime → 一律轉成 UTC 後輸出
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer

UTC = timezone.utc
# 台北時區（UTC+8）。用於後端需要「台北當地日曆日期」的直接顯示字串
# （例如問候語中的會議日期）；API 邊界的機器可讀時間仍以 UTC 輸出交由前端換算。
TAIPEI = timezone(timedelta(hours=8))


def to_taipei(dt: datetime) -> datetime:
    """轉成台北時間（naive 視為 UTC）。"""
    return to_utc_aware(dt).astimezone(TAIPEI)


def to_utc_aware(dt: datetime) -> datetime:
    """將 naive datetime 視為 UTC；aware datetime 轉成 UTC。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """序列化為帶 `Z` 的 UTC ISO8601 字串；None → None。"""
    if dt is None:
        return None
    aware = to_utc_aware(dt)
    # 統一以 'Z' 表示 UTC，避免 '+00:00' 與 'Z' 混用
    return aware.isoformat().replace("+00:00", "Z")


def _serialize_utc(dt: datetime) -> str:
    return to_utc_iso(dt)  # type: ignore[return-value]


# Pydantic v2 annotated type：套用於 schema 的 datetime 輸出欄位，
# 確保序列化（python 與 json 兩種模式）皆輸出帶 'Z' 的 UTC 字串。
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(_serialize_utc, return_type=str, when_used="always"),
]
