"""
RAG context chunker — Sentence Window Expansion for retrieved segments.

設計目標（劇本 2 互補擴充）：
  把 top-K retrieve 出來的命中 segment 各自向前後擴展 N 個 segments，
  提供 LLM 更完整的上下文（時間順序連續），提升 grounded answer 品質。

不做（留 Phase B/C）：
  - 三層 hierarchical chunking (sentence / topic / meeting)
  - chunks 持久化到 DB schema
  - BM25 / hybrid search retrieval
  - Cross-encoder reranking

API:
  expanded_rows = expand_with_context(db, retrieved_rows, window=2)
  → 每個 ExpandedRow.content 已包含前 window + 命中 + 後 window 個 segments 的串接

複雜度：O(N+1) DB queries（1 batch query 取 order map + N 個 contextual range queries）
       對 top_k=10 約 11 次 round-trip。可接受。批次優化留給未來性能瓶頸時再做。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class ExpandedRow:
    """
    Retrieve row 加上 sentence-window context，用於組 grounded prompt。

    與原始 SQL row 的差異：
      - content 是「擴展後」的完整文字（含前後文 segments）
      - 多 hit_marker 標記哪一段是命中的中心
    """

    id: str
    meeting_id: str
    meeting_title: Optional[str]
    speaker: Optional[str]
    start_time: Optional[float]
    end_time: Optional[float]
    content: str  # ⭐ 擴展後的內容（已含前後文）
    distance: float  # 原始 retrieve cosine distance
    expansion_size: int = 0  # 實際擴展了幾個 neighbour（含命中本身）

    # 保留原始命中段，方便偵錯與 frontend 高亮
    hit_content: str = ""

    # 額外欄位由 caller 處理（如 content_polished/content_raw）
    extra: dict = field(default_factory=dict)


def _get_segment_orders(db: Session, segment_ids: List[str]) -> dict:
    """
    Batch query 取得每個 segment 的 (meeting_id, order)。

    Returns:
        {segment_id: (meeting_id, order_int)}
    """
    if not segment_ids:
        return {}

    placeholders = ",".join(f":id_{i}" for i in range(len(segment_ids)))
    sql = text(
        f'SELECT id, meeting_id, "order" '
        f"FROM transcript_segments "
        f"WHERE id IN ({placeholders})"
    )
    params = {f"id_{i}": sid for i, sid in enumerate(segment_ids)}

    return {
        r.id: (r.meeting_id, r.order)
        for r in db.execute(sql, params).fetchall()
    }


def _fetch_neighbours(
    db: Session,
    meeting_id: str,
    center_order: int,
    window: int,
) -> List[Any]:
    """
    撈 [center_order - window, center_order + window] 範圍的 segments，
    依 order 升序回傳。
    """
    sql = text(
        'SELECT id, speaker, start_time, end_time, content_polished, '
        'content_raw, "order" '
        'FROM transcript_segments '
        'WHERE meeting_id = :meeting_id '
        '  AND "order" BETWEEN :lo AND :hi '
        'ORDER BY "order"'
    )
    return db.execute(
        sql,
        {
            "meeting_id": meeting_id,
            "lo": center_order - window,
            "hi": center_order + window,
        },
    ).fetchall()


def _format_expanded_content(
    neighbours: List[Any],
    center_order: int,
) -> str:
    """
    把 neighbour rows 串成可讀格式：
      [Speaker A] 前文一句...
    ➤ [Speaker B] 命中段落...
      [Speaker A] 後文一句...

    "➤" 用於標記命中段中心，幫助 LLM 知道哪段是 retrieve 命中。
    """
    parts = []
    for nb in neighbours:
        speaker = getattr(nb, "speaker", None) or ""
        content = (
            getattr(nb, "content_polished", None)
            or getattr(nb, "content_raw", None)
            or ""
        )
        speaker_prefix = f"[{speaker}] " if speaker else ""
        marker = "➤ " if nb.order == center_order else "  "
        parts.append(f"{marker}{speaker_prefix}{content}")
    return "\n".join(parts)


def expand_with_context(
    db: Session,
    retrieved_rows: List[Any],
    window: int = 2,
) -> List[ExpandedRow]:
    """
    對每個 retrieved row 向前後擴展 window 個 segments，組成 ExpandedRow。

    Args:
        db: SQLAlchemy session
        retrieved_rows: routes/rag.py `_find_similar_segments` 回傳的 row list
                        必須含欄位: id, meeting_id, speaker, start_time, end_time,
                        content_polished, content_raw, meeting_title, distance
        window: 前後各取 N 個 segments；window=0 表示不擴展（原樣返回 ExpandedRow 包覆）

    Returns:
        List[ExpandedRow]，順序與 retrieved_rows 相同；保證每個 retrieved
        row 都會有對應 ExpandedRow（即使找不到 neighbours 也不會 drop）

    Notes:
        - window<0 視同 0（防呆）
        - 找不到 order 的 row（資料異常）會 fallback 用原 content
    """
    if not retrieved_rows:
        return []

    if window < 0:
        window = 0

    # Step 1: batch query 取每個 retrieved row 的 (meeting_id, order)
    seg_ids = [str(r.id) for r in retrieved_rows]
    orders_map = _get_segment_orders(db, seg_ids)

    expanded_list: List[ExpandedRow] = []

    for row in retrieved_rows:
        sid = str(row.id)

        # Fallback: 若找不到 order（資料髒），原樣包成 ExpandedRow
        if sid not in orders_map:
            content = (
                getattr(row, "content_polished", None)
                or getattr(row, "content_raw", None)
                or ""
            )
            expanded_list.append(
                ExpandedRow(
                    id=sid,
                    meeting_id=getattr(row, "meeting_id", ""),
                    meeting_title=getattr(row, "meeting_title", None),
                    speaker=getattr(row, "speaker", None),
                    start_time=getattr(row, "start_time", None),
                    end_time=getattr(row, "end_time", None),
                    content=content,
                    distance=float(getattr(row, "distance", 0.0)),
                    expansion_size=1,
                    hit_content=content,
                )
            )
            continue

        meeting_id, center_order = orders_map[sid]

        # window=0 時就只返回命中段本身的內容；用 _fetch_neighbours(0) 仍 work
        neighbours = _fetch_neighbours(db, meeting_id, center_order, window)

        if not neighbours:
            # 極端情況：DB 內找不到（race condition）→ fallback 原 content
            content = (
                getattr(row, "content_polished", None)
                or getattr(row, "content_raw", None)
                or ""
            )
            hit_content = content
        else:
            content = _format_expanded_content(neighbours, center_order)
            # 找出命中段的純文字（給 frontend 高亮）
            hit_content = ""
            for nb in neighbours:
                if nb.order == center_order:
                    hit_content = (
                        getattr(nb, "content_polished", None)
                        or getattr(nb, "content_raw", None)
                        or ""
                    )
                    break

        expanded_list.append(
            ExpandedRow(
                id=sid,
                meeting_id=meeting_id,
                meeting_title=getattr(row, "meeting_title", None),
                speaker=getattr(row, "speaker", None),
                start_time=getattr(row, "start_time", None),
                end_time=getattr(row, "end_time", None),
                content=content,
                distance=float(getattr(row, "distance", 0.0)),
                expansion_size=len(neighbours),
                hit_content=hit_content,
            )
        )

    return expanded_list
