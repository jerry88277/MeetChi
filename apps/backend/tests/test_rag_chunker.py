"""
Unit tests for app.rag.chunker — sentence-window expansion.

Run:
  cd apps/backend
  pytest tests/test_rag_chunker.py -v

Strategy: mock SQLAlchemy session 與 execute().fetchall() 結果，不依賴真實 DB。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.rag.chunker import (
    ExpandedRow,
    expand_with_context,
    _format_expanded_content,
)


# ============================================
# Helpers
# ============================================
def _retrieved_row(
    sid="seg-1",
    meeting_id="m-1",
    meeting_title="A",
    speaker="Alice",
    start_time=0.0,
    end_time=5.0,
    content_polished="hit content",
    content_raw=None,
    distance=0.2,
):
    return SimpleNamespace(
        id=sid,
        meeting_id=meeting_id,
        meeting_title=meeting_title,
        speaker=speaker,
        start_time=start_time,
        end_time=end_time,
        content_polished=content_polished,
        content_raw=content_raw,
        distance=distance,
    )


def _neighbour(order: int, speaker="X", content="text"):
    return SimpleNamespace(
        id=f"n-{order}",
        speaker=speaker,
        start_time=order * 5.0,
        end_time=(order + 1) * 5.0,
        content_polished=content,
        content_raw=None,
        order=order,
    )


def _make_db(orders_map: dict, neighbour_map: dict) -> MagicMock:
    """
    Create a mock db that:
      - First execute(...) call returns segment-id → (meeting_id, order) lookup
      - Subsequent calls return per-meeting neighbour rows from neighbour_map
    """
    db = MagicMock()

    # 先決定 execute 的 fetchall 序列
    # 因為 chunker 先 batch query orders，再對每個 row query neighbours
    orders_rows = [
        SimpleNamespace(id=sid, meeting_id=mid, order=order)
        for sid, (mid, order) in orders_map.items()
    ]

    fetchall_results = [orders_rows]
    # 每個 retrieved row 對應一次 neighbour query
    for sid in orders_map.keys():
        meeting_id, order = orders_map[sid]
        fetchall_results.append(neighbour_map.get((meeting_id, order), []))

    def execute_side_effect(*args, **kwargs):
        result = MagicMock()
        result.fetchall.return_value = fetchall_results.pop(0) if fetchall_results else []
        return result

    db.execute.side_effect = execute_side_effect
    return db


# ============================================
# ExpandedRow dataclass
# ============================================
class TestExpandedRow:
    def test_construct_with_required(self):
        r = ExpandedRow(
            id="x",
            meeting_id="m",
            meeting_title="A",
            speaker="S",
            start_time=0.0,
            end_time=1.0,
            content="c",
            distance=0.5,
        )
        assert r.id == "x"
        assert r.expansion_size == 0
        assert r.hit_content == ""
        assert r.extra == {}


# ============================================
# expand_with_context — boundary
# ============================================
class TestExpandBoundary:
    def test_empty_input_returns_empty(self):
        db = MagicMock()
        result = expand_with_context(db, [], window=2)
        assert result == []
        db.execute.assert_not_called()

    def test_negative_window_treated_as_zero(self):
        # window=-5 → 視同 0，仍會做 neighbour query (range [0,0])
        rows = [_retrieved_row(sid="seg-1")]
        db = _make_db(
            orders_map={"seg-1": ("m-1", 5)},
            neighbour_map={("m-1", 5): [_neighbour(5, content="hit")]},
        )
        result = expand_with_context(db, rows, window=-5)
        assert len(result) == 1
        assert result[0].expansion_size == 1


# ============================================
# expand_with_context — happy path
# ============================================
class TestExpandHappyPath:
    def test_single_row_expanded(self):
        rows = [_retrieved_row(sid="seg-1")]
        db = _make_db(
            orders_map={"seg-1": ("m-1", 5)},
            neighbour_map={
                ("m-1", 5): [
                    _neighbour(3, speaker="A", content="前文 -2"),
                    _neighbour(4, speaker="B", content="前文 -1"),
                    _neighbour(5, speaker="C", content="命中段"),
                    _neighbour(6, speaker="D", content="後文 +1"),
                    _neighbour(7, speaker="E", content="後文 +2"),
                ]
            },
        )
        result = expand_with_context(db, rows, window=2)

        assert len(result) == 1
        er = result[0]
        assert er.id == "seg-1"
        assert er.expansion_size == 5
        assert "前文 -2" in er.content
        assert "前文 -1" in er.content
        assert "命中段" in er.content
        assert "後文 +1" in er.content
        assert "後文 +2" in er.content
        # 命中段該被 ➤ 標記
        assert "➤" in er.content
        assert er.hit_content == "命中段"

    def test_multiple_rows_each_expanded(self):
        rows = [_retrieved_row(sid="s1"), _retrieved_row(sid="s2")]
        db = _make_db(
            orders_map={"s1": ("m-1", 1), "s2": ("m-2", 10)},
            neighbour_map={
                ("m-1", 1): [_neighbour(1, content="row1 hit")],
                ("m-2", 10): [_neighbour(10, content="row2 hit")],
            },
        )
        result = expand_with_context(db, rows, window=1)

        assert len(result) == 2
        assert result[0].id == "s1"
        assert result[1].id == "s2"
        assert "row1 hit" in result[0].content
        assert "row2 hit" in result[1].content


# ============================================
# expand_with_context — fallback paths
# ============================================
class TestExpandFallback:
    def test_missing_order_falls_back_to_raw_content(self):
        # orders_map 沒這個 sid → fallback 用 row 原 content
        rows = [_retrieved_row(sid="seg-orphan", content_polished="orphan content")]
        db = _make_db(orders_map={}, neighbour_map={})
        result = expand_with_context(db, rows, window=2)

        assert len(result) == 1
        assert result[0].id == "seg-orphan"
        assert result[0].content == "orphan content"
        assert result[0].hit_content == "orphan content"
        # 沒擴展發生
        assert result[0].expansion_size == 1

    def test_no_neighbours_falls_back(self):
        # orders 找到，但 fetch_neighbours 回空 list
        rows = [_retrieved_row(sid="seg-x", content_polished="raw text")]
        db = _make_db(
            orders_map={"seg-x": ("m-1", 5)},
            neighbour_map={("m-1", 5): []},
        )
        result = expand_with_context(db, rows, window=2)

        assert len(result) == 1
        assert "raw text" in result[0].content

    def test_uses_content_raw_if_no_polished(self):
        rows = [_retrieved_row(sid="s1", content_polished=None, content_raw="raw only")]
        db = _make_db(orders_map={}, neighbour_map={})
        result = expand_with_context(db, rows, window=2)

        assert result[0].content == "raw only"


# ============================================
# _format_expanded_content
# ============================================
class TestFormatExpandedContent:
    def test_marks_center_with_arrow(self):
        neighbours = [
            _neighbour(1, speaker="A", content="a"),
            _neighbour(2, speaker="B", content="b"),
            _neighbour(3, speaker="C", content="c"),
        ]
        content = _format_expanded_content(neighbours, center_order=2)
        lines = content.split("\n")
        assert len(lines) == 3
        # 第 2 行（order=2）應有 ➤
        assert "➤" in lines[1]
        # 其他行用空白縮排
        assert lines[0].startswith("  ")
        assert lines[2].startswith("  ")

    def test_speaker_prefix(self):
        neighbours = [_neighbour(1, speaker="王經理", content="hi")]
        content = _format_expanded_content(neighbours, center_order=1)
        assert "[王經理]" in content
        assert "hi" in content

    def test_no_speaker_no_brackets(self):
        neighbours = [_neighbour(1, speaker=None, content="hi")]
        content = _format_expanded_content(neighbours, center_order=1)
        assert "[None]" not in content
        assert "[]" not in content
        assert "hi" in content
