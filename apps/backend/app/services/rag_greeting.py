"""
RAG Greeting Service (2026-06-08)
Generates personalized "five-star hotel check-in" greeting for the RAG workspace.
Approach: Approach A — deterministic DB + template (no LLM, low latency).
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def resolve_display_name(db: Session, user_upn: str) -> str:
    """Get display name from users table; fallback to upn prefix."""
    try:
        row = db.execute(
            text("SELECT display_name FROM users WHERE ad_upn = :upn"),
            {"upn": user_upn}
        ).fetchone()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.warning(f"resolve_display_name failed: {e}")
    return user_upn.split("@")[0]


def get_accessible_meeting_stats(db: Session, user_upn: str) -> Dict[str, Any]:
    """Count meetings accessible to user and get last meeting date."""
    try:
        row = db.execute(text("""
            SELECT COUNT(DISTINCT m.id), MAX(m.created_at)
            FROM meetings m
            JOIN meeting_participants mp ON mp.meeting_id = m.id AND mp.user_upn = :upn
            WHERE m.deleted_at IS NULL
        """), {"upn": user_upn}).fetchone()
        if row:
            return {"meeting_count": int(row[0] or 0), "last_date": row[1]}
    except Exception as e:
        logger.warning(f"get_accessible_meeting_stats failed: {e}")
    return {"meeting_count": 0, "last_date": None}


def get_recent_meetings_for_greeting(db: Session, user_upn: str, limit: int = 10) -> List[Dict]:
    """Get recent completed meetings with summary_json for topic extraction."""
    try:
        rows = db.execute(text("""
            SELECT m.id, m.title, m.created_at, m.summary_json
            FROM meetings m
            JOIN meeting_participants mp ON mp.meeting_id = m.id AND mp.user_upn = :upn
            WHERE m.deleted_at IS NULL
              AND m.summary_json IS NOT NULL
            ORDER BY m.created_at DESC
            LIMIT :limit
        """), {"upn": user_upn, "limit": limit}).fetchall()
        return [{"id": r[0], "title": r[1], "created_at": r[2], "summary_json": r[3]} for r in rows]
    except Exception as e:
        logger.warning(f"get_recent_meetings_for_greeting failed: {e}")
    return []


def get_pending_action_count(db: Session, user_upn: str) -> int:
    """Count pending action items for user across all meetings."""
    try:
        # Try normalized table first
        row = db.execute(text("""
            SELECT COUNT(*)
            FROM meeting_action_items mai
            JOIN meeting_participants mp ON mp.meeting_id = mai.meeting_id AND mp.user_upn = :upn
            WHERE mai.status = 'pending'
        """), {"upn": user_upn}).fetchone()
        if row:
            return int(row[0] or 0)
    except Exception as e:
        logger.warning(f"get_pending_action_count failed (table may not exist yet): {e}")
    return 0


def extract_top_topics(meetings: List[Dict], max_topics: int = 3) -> List[str]:
    """
    Extract top recurring topics from meeting summary_json.
    Deterministic: count frequency of chapter titles / speaker topics / meeting titles.
    """
    import json
    from collections import Counter

    candidates = Counter()
    for m in meetings:
        sj = m.get("summary_json")
        if not sj:
            continue
        if isinstance(sj, str):
            try:
                sj = json.loads(sj)
            except Exception:
                continue
        if not isinstance(sj, dict):
            continue

        # Chapter titles
        for ch in (sj.get("chapters") or []):
            t = (ch.get("title") or "").strip()
            if len(t) > 2:
                candidates[t] += 2  # weight higher

        # Speaker contribution topics
        for sc in (sj.get("speaker_contributions") or []):
            for topic in (sc.get("main_topics") or []):
                t = str(topic).strip()
                if len(t) > 2:
                    candidates[t] += 1

        # Meeting title words (lower weight)
        title = (m.get("title") or "").strip()
        if len(title) > 3:
            candidates[title] += 1

    # Filter trivial, return top N
    filtered = [(k, v) for k, v in candidates.items() if len(k) >= 3]
    filtered.sort(key=lambda x: -x[1])
    return [k for k, _ in filtered[:max_topics]]


def build_greeting_text(display_name: str, meeting_count: int, top_topics: List[str],
                         last_meeting: Optional[Dict], pending_count: int) -> str:
    """Build template-based greeting text (no LLM)."""
    if meeting_count == 0:
        return f"歡迎使用 ChiMemo，{display_name}。上傳第一場會議後，我可以幫您彙整跨會議的決策與待辦。"

    parts = [f"歡迎回來，{display_name}。"]

    if top_topics:
        topics_str = "、".join(top_topics[:3])
        parts.append(f"根據您過去 {meeting_count} 場會議，您最常討論的主題是 {topics_str}。")
    else:
        parts.append(f"您已累積 {meeting_count} 場會議記錄。")

    if last_meeting:
        title = last_meeting.get("title", "")
        key_actions = last_meeting.get("key_actions", [])
        if title:
            parts.append(f"上次是「{title}」")
            if key_actions:
                parts.append(f"，提到了 {key_actions[0]}。")
            else:
                parts.append("。")

    if pending_count > 0:
        parts.append(f"目前有 {pending_count} 個待追蹤事項，需要我幫您整理嗎？")

    return "".join(parts)


def build_suggested_questions(top_topics: List[str], last_meeting: Optional[Dict],
                               pending_count: int) -> List[str]:
    """Generate 3 contextual suggested questions."""
    questions = []

    if last_meeting and last_meeting.get("key_actions"):
        q = f"上次提到的「{last_meeting['key_actions'][0]}」後來有什麼進展？"
        questions.append(q)

    if top_topics:
        q = f"彙整所有會議中關於「{top_topics[0]}」的討論結論"
        questions.append(q)

    if pending_count > 0:
        questions.append("有哪些跨多場會議的待辦事項還沒有解決？")
    elif top_topics and len(top_topics) > 1:
        questions.append(f"比較不同會議對「{top_topics[1]}」的看法有什麼共識或分歧？")

    # Fill to 3 with generic fallbacks
    fallbacks = [
        "彙整最近所有會議的關鍵決策",
        "有哪些事項在多場會議中反覆出現？",
        "各場會議提到哪些尚未完成的承諾？",
    ]
    for fb in fallbacks:
        if len(questions) >= 3:
            break
        if fb not in questions:
            questions.append(fb)

    return questions[:3]


def get_last_meeting_summary(meetings: List[Dict]) -> Optional[Dict]:
    """Extract last meeting's title, date, and key actions."""
    import json
    if not meetings:
        return None
    m = meetings[0]
    sj = m.get("summary_json")
    if isinstance(sj, str):
        try:
            sj = json.loads(sj)
        except Exception:
            sj = {}
    if not isinstance(sj, dict):
        sj = {}

    key_actions = []
    for item in (sj.get("action_items") or [])[:2]:
        if isinstance(item, str) and item.strip():
            key_actions.append(item.strip())
    for item in (sj.get("next_steps") or [])[:2]:
        if isinstance(item, dict):
            t = (item.get("action") or item.get("text") or "").strip()
            if t:
                key_actions.append(t)
        elif isinstance(item, str) and item.strip():
            key_actions.append(item.strip())

    date_str = ""
    if m.get("created_at"):
        try:
            dt = m["created_at"]
            if hasattr(dt, "strftime"):
                date_str = dt.strftime("%Y-%m-%d")
            else:
                date_str = str(dt)[:10]
        except Exception:
            pass

    return {
        "title": m.get("title", ""),
        "date": date_str,
        "key_actions": key_actions[:2],
    }


def build_greeting_payload(db: Session, user_upn: str) -> Dict[str, Any]:
    """
    Main entry point. Build the full greeting payload for a user.
    Always returns a valid dict — never raises (all errors caught internally).
    """
    try:
        display_name = resolve_display_name(db, user_upn)
        stats = get_accessible_meeting_stats(db, user_upn)
        meeting_count = stats["meeting_count"]

        recent = get_recent_meetings_for_greeting(db, user_upn, limit=10)
        top_topics = extract_top_topics(recent)
        last_meeting = get_last_meeting_summary(recent)
        pending_count = get_pending_action_count(db, user_upn)

        greeting_text = build_greeting_text(
            display_name, meeting_count, top_topics, last_meeting, pending_count
        )
        suggested_questions = build_suggested_questions(top_topics, last_meeting, pending_count)

        return {
            "display_name": display_name,
            "meeting_count": meeting_count,
            "top_topics": top_topics,
            "last_meeting": last_meeting,
            "pending_action_count": pending_count,
            "greeting_text": greeting_text,
            "suggested_questions": suggested_questions,
        }
    except Exception as e:
        logger.error(f"build_greeting_payload failed for {user_upn}: {e}", exc_info=True)
        return {
            "display_name": user_upn.split("@")[0],
            "meeting_count": 0,
            "top_topics": [],
            "last_meeting": None,
            "pending_action_count": 0,
            "greeting_text": "歡迎使用 ChiMemo。上傳第一場會議後，我可以幫您彙整跨會議的討論與待辦。",
            "suggested_questions": [
                "彙整最近所有會議的關鍵決策",
                "有哪些事項在多場會議中反覆出現？",
                "各場會議提到哪些尚未完成的承諾？",
            ],
        }
