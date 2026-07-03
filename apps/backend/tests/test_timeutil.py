"""Tests for UTC datetime serialization (2026-07-03 timezone fix)."""
from datetime import datetime, timezone, timedelta

from app.timeutil import to_utc_iso, to_utc_aware, to_taipei, TAIPEI
from app.schemas import MeetingListItem


def test_naive_datetime_treated_as_utc():
    dt = datetime(2026, 7, 3, 2, 4, 9, 439516)
    assert to_utc_iso(dt) == "2026-07-03T02:04:09.439516Z"


def test_aware_datetime_converted_to_utc():
    dt = datetime(2026, 7, 3, 10, 4, 9, tzinfo=TAIPEI)  # 10:04 台北 == 02:04 UTC
    assert to_utc_iso(dt) == "2026-07-03T02:04:09Z"


def test_none_returns_none():
    assert to_utc_iso(None) is None


def test_to_taipei_offsets_by_8h():
    dt = datetime(2026, 7, 3, 2, 4, 0)  # naive UTC
    tp = to_taipei(dt)
    assert tp.strftime("%Y-%m-%d %H:%M") == "2026-07-03 10:04"


def test_to_utc_aware_naive():
    dt = datetime(2026, 1, 1, 0, 0, 0)
    assert to_utc_aware(dt).tzinfo == timezone.utc


def test_schema_serializes_with_z_suffix():
    dt = datetime(2026, 7, 3, 2, 4, 9, 439516)
    m = MeetingListItem(
        id="x", title="錄製", status="COMPLETED",
        created_at=dt, updated_at=dt, duration=143.0,
        audio_url=None, summary_json=None,
    )
    dumped = m.model_dump(mode="json")
    assert dumped["created_at"].endswith("Z")
    assert dumped["created_at"] == "2026-07-03T02:04:09.439516Z"
