"""
RAG grounding prompt — NotebookLM-style strict grounding with 4-level confidence.

設計目標（劇本 2 互補擴充）：
  1. **嚴格 grounded**：回答只用提供的 [來源N] 段落，禁止外推
  2. **強制引用**：每個事實主張必須附 [來源N] 標記
  3. **誠實拒答**：citations 不足以回答時，明確拒答而非編造
  4. **confidence 自我評估**：4 級（high / medium / low / no_answer）
  5. **禁止 markdown**：純文字輸出

取代 routes/rag.py 既有的 _build_rag_prompt（軟規則、無 confidence）。

輸出 JSON contract:
  {
    "answer": str,
    "used_citations": List[int],
    "confidence": "high" | "medium" | "low" | "no_answer"
  }
"""

from __future__ import annotations

from typing import Any, List, Optional


# ============================================
# Constants
# ============================================
CONFIDENCE_LEVELS = ("high", "medium", "low", "no_answer")
DEFAULT_CONFIDENCE = "no_answer"

# 對話歷史控制：避免過長 prompt + 防 prompt injection
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS_PER_TURN = 200


STRICT_GROUNDING_SYSTEM_PROMPT = """你是 MeetChi 跨會議檢索問答助手。**嚴格遵守以下 5 條規則**：

【規則 1：只用 citations】
回答必須完全基於下方提供的 [來源N] 段落。**禁止**引用 citations 以外的任何知識（即使你知道答案）。

【規則 2：強制引用】
每個事實主張必須在句末附 [來源N] 標記。沒有 citation 支援的描述一律不寫進 answer。

【規則 3：誠實拒答】
如果 citations 不足以回答問題，**直接寫**「根據現有會議記錄，無法明確回答此問題」並把 confidence 設為 "no_answer"。**禁止**編造、含糊、轉移話題。

【規則 4：confidence 自我評估】
回傳以下 4 級之一，反映你對 answer 的信心：
- "high"      : citations 直接、完整、明確支援答案
- "medium"    : 多數 citations 支援，但有細節不全或邊緣情況
- "low"       : citations 只間接相關，需做合理推斷
- "no_answer" : citations 完全不相關，已執行規則 3 拒答

【規則 5：禁止 markdown】
純文字輸出，僅可用 \\n 換行。**禁止** ** / # / * / - / > 等 markdown 符號。

輸出格式：嚴格 JSON
{
  "answer": "<純文字回答，含 [來源N] 標記>",
  "used_citations": [<引用過的來源編號 list, e.g. [1, 3]>],
  "confidence": "high|medium|low|no_answer"
}"""


def _format_time(seconds: Optional[float]) -> str:
    """Format seconds as MM:SS string. Returns empty if None."""
    if seconds is None:
        return ""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f" [{mins:02d}:{secs:02d}]"


def _format_history(history: Optional[List[Any]]) -> str:
    """
    把 conversation history 壓縮成 prompt block。

    控制：
      - 只取最近 MAX_HISTORY_TURNS 輪
      - 每輪 user.text 截至 MAX_HISTORY_CHARS_PER_TURN
      - 防 prompt injection: 字面貼出 user.text，不執行任何 LLM 化處理
    """
    if not history:
        return ""

    # 只看最近 N 輪
    recent = history[-MAX_HISTORY_TURNS:]

    parts = []
    for msg in recent:
        # msg 可能是 ChatMessage / dict / 任何有 role + text 的物件
        role_raw = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else "")
        text_raw = getattr(msg, "text", None) or (msg.get("text") if isinstance(msg, dict) else "")
        role_label = "User" if str(role_raw).lower() == "user" else "AI"
        truncated = str(text_raw)[:MAX_HISTORY_CHARS_PER_TURN]
        parts.append(f"{role_label}: {truncated}")

    return "對話脈絡（最近 {n} 輪）：\n{body}\n\n".format(
        n=len(parts),
        body="\n".join(parts),
    )


def build_grounded_prompt(
    question: str,
    citations: List[Any],
    history: Optional[List[Any]] = None,
) -> str:
    """
    組裝 grounded prompt: system rules + citations block + history + question.

    Args:
        question: 使用者問題（已經過 contextualization）
        citations: List of objects with attrs (meeting_title, speaker, start_time, content)
                   接受 routes/rag.py 的 Citation 或本模組的 ExpandedRow
        history: Optional list of {role, text} 對話歷史，會被自動截短與限輪數

    Returns:
        完整 prompt 字串，可直接送 Gemini

    Raises:
        無 — 任何屬性缺失都用 fallback (empty string / None handling)
    """
    # 拼 citations block
    context_parts = []
    for i, c in enumerate(citations, 1):
        meeting_title = getattr(c, "meeting_title", None) or "未命名會議"
        speaker = getattr(c, "speaker", None) or ""
        start_time = getattr(c, "start_time", None)
        content = getattr(c, "content", None) or ""

        speaker_info = f" ({speaker})" if speaker else ""
        time_info = _format_time(start_time)

        context_parts.append(
            f"[來源{i}] 會議「{meeting_title}」{speaker_info}{time_info}:\n{content}"
        )

    context_block = "\n\n".join(context_parts) if context_parts else "（無相關段落）"

    history_block = _format_history(history)

    # 組裝最終 prompt
    return f"""{STRICT_GROUNDING_SYSTEM_PROMPT}

---
**Citations 段落**：

{context_block}

---
{history_block}**問題**：{question}

**請回答（嚴格遵守 5 條規則）**："""
