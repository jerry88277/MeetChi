"""
RAG Query Intent Router (Q5, 2026-07-03)

問題背景（稽核 Q5 根因 c）：
  純向量檢索對「單場會議」的提問會過度召回、擴散成跨場引用。根因是缺少一層
  「意圖器」在語意搜尋『之前』先用結構化條件（日期 / 機密 / 會議名 / 講者）縮小範圍。

本模組職責：
  1. classify_query_intent()：用 Gemini 把自然語言問題解析成結構化 QueryIntent
     （scope / topic / date_after / date_before / speaker_hints / meeting_hints /
      include_confidential）。永不 raise —— 任何錯誤都 fallback 成「passthrough」
     （cross_meeting、topic=原問題、無過濾），確保不改變現行召回。
  2. build_meeting_sql_filters()：純函式，把 QueryIntent 轉成一段可安全內插的
     SQL WHERE fragment（欄位名固定、值全走 bound params）+ 對應 params dict。
     方便被 routes/rag.py 的多個查詢分支共用，且可獨立單元測試。

設計對齊既有 app.intent_classifier（strict JSON / 低溫 / graceful fallback / 可 mock）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ============================================
# Constants
# ============================================
# 查詢意圖範疇（MECE）：驅動下游縮域策略
QUERY_SCOPES = ("single_meeting", "cross_meeting", "person_centric", "action_items", "unknown")
DEFAULT_SCOPE = "cross_meeting"  # 未知時採現行「跨會議搜尋」行為，不縮限召回

# 控制成本：查詢句通常很短，截斷保護即可
MAX_QUERY_CHARS = 1000

# UTC+8（Asia/Taipei）——對齊 agents.md 時區規則，日期相對詞以台北「今天」為基準
TAIPEI_TZ = timezone(timedelta(hours=8))


CLASSIFY_QUERY_PROMPT = """你是「跨會議檢索」的查詢意圖分析器。使用者會用自然語言對他過去的會議記錄提問。
請把問題解析成結構化 JSON，供系統在語意搜尋前先縮小範圍。

今天的日期（台北時間 UTC+8）：{today}

請判斷並回傳以下欄位：
- scope：問題範疇，必須是下列之一
    single_meeting  : 針對某一場特定會議（提到會議名稱、某次會議、那場會議等）
    cross_meeting   : 跨多場會議的彙整、比較、共識/分歧
    person_centric  : 以某個「人」為中心（某人說了什麼、某人負責什麼）
    action_items    : 詢問待辦/待追蹤/未完成事項
    unknown         : 無法判斷
- topic：把問題濃縮成「乾淨的搜尋主題句」，去除「幫我彙整/請問/後來怎樣了」等贅詞，
         保留核心名詞與語意（用於語意向量搜尋）。務必是完整可搜尋的句子，不可空白。
- date_after：若問題含時間範圍（如「最近」「上週」「六月」「今年」），回推算出的起始日期，
             格式嚴格 YYYY-MM-DD；無時間限定則回傳 null。
- date_before：時間範圍結束日期（不含），格式 YYYY-MM-DD；無則 null。
- speaker_hints：問題中提到的人名（真實姓名），list of string；無則空陣列。
- meeting_hints：問題中提到的會議名稱關鍵詞，list of string；無則空陣列。
- include_confidential：使用者是否明確表示要包含機密/敏感會議（例如點名財務、薪資、合約）。
                       預設 false；只有在使用者明確指向敏感主題時才 true。
- confidence：你對本次解析的信心 0.0~1.0。

只回傳純 JSON，不附任何說明，格式範例：
{{"scope":"cross_meeting","topic":"RAG 架構的共識與分歧","date_after":null,"date_before":null,"speaker_hints":[],"meeting_hints":[],"include_confidential":false,"confidence":0.8}}

使用者問題：
{question}"""


# ============================================
# Output schema
# ============================================
class QueryIntent(BaseModel):
    """查詢意圖解析結果。任何錯誤情境也會回傳此型別（passthrough fallback）。"""

    scope: str = Field(DEFAULT_SCOPE, description="查詢範疇，屬於 QUERY_SCOPES")
    topic: str = Field(..., min_length=1, description="乾淨的搜尋主題句（供向量搜尋）")
    date_after: Optional[str] = Field(None, description="起始日期 YYYY-MM-DD 或 None")
    date_before: Optional[str] = Field(None, description="結束日期(不含) YYYY-MM-DD 或 None")
    speaker_hints: List[str] = Field(default_factory=list)
    meeting_hints: List[str] = Field(default_factory=list)
    include_confidential: bool = Field(False)
    confidence: float = Field(0.0, ge=0.0, le=1.0)

    @field_validator("scope")
    @classmethod
    def _normalize_scope(cls, v: str) -> str:
        return v if v in QUERY_SCOPES else DEFAULT_SCOPE

    @field_validator("date_after", "date_before")
    @classmethod
    def _validate_iso_date(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except (ValueError, TypeError):
            # 非法日期格式一律忽略（不縮域比錯誤縮域安全）
            return None


def passthrough_intent(question: str) -> QueryIntent:
    """Fallback：不縮域、topic=原問題，維持現行檢索行為。"""
    return QueryIntent(
        scope=DEFAULT_SCOPE,
        topic=(question or "").strip() or "（空白查詢）",
        confidence=0.0,
    )


# ============================================
# Public API
# ============================================
def classify_query_intent(
    question: str,
    client: Any,  # google.genai.Client（避免硬 import）
    model: str = "gemini-2.5-flash-lite",
    now: Optional[datetime] = None,
) -> QueryIntent:
    """
    用 Gemini 解析查詢意圖。**永不 raise**：任何 API / JSON / schema 錯誤都回
    passthrough_intent(question)，確保下游檢索至少維持現況。

    Args:
        question: 使用者問題（已經過 contextualization）
        client:   已初始化的 google.genai client
        model:    Gemini model id（預設 flash-lite，低成本）
        now:      注入「現在時間」以利測試；預設台北時間 now

    Returns:
        QueryIntent（topic 一定非空）
    """
    q = (question or "").strip()
    if not q:
        return passthrough_intent(question)

    today = (now or datetime.now(TAIPEI_TZ)).strftime("%Y-%m-%d")
    prompt = CLASSIFY_QUERY_PROMPT.format(today=today, question=q[:MAX_QUERY_CHARS])

    raw_text = ""
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "max_output_tokens": 400,
            },
        )
        raw_text = response.text or ""
        data = json.loads(raw_text)

        # topic 缺失/空白 → 用原問題，確保向量搜尋有輸入
        topic = str(data.get("topic") or "").strip() or q

        intent = QueryIntent(
            scope=str(data.get("scope") or DEFAULT_SCOPE),
            topic=topic,
            date_after=data.get("date_after"),
            date_before=data.get("date_before"),
            speaker_hints=[str(s).strip() for s in (data.get("speaker_hints") or []) if str(s).strip()],
            meeting_hints=[str(s).strip() for s in (data.get("meeting_hints") or []) if str(s).strip()],
            include_confidential=bool(data.get("include_confidential", False)),
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0) or 0.0))),
        )
        logger.info(
            f"[query_intent] scope={intent.scope} topic={intent.topic!r} "
            f"date=[{intent.date_after},{intent.date_before}] "
            f"speakers={intent.speaker_hints} meetings={intent.meeting_hints} "
            f"inc_conf={intent.include_confidential} conf={intent.confidence:.2f}"
        )
        return intent

    except json.JSONDecodeError as e:
        logger.warning(f"[query_intent] JSON parse fail: {e}; raw={raw_text[:200]!r}")
        return passthrough_intent(question)
    except Exception as e:
        logger.warning(f"[query_intent] LLM call failed: {type(e).__name__}: {e}")
        return passthrough_intent(question)


def build_meeting_sql_filters(
    intent: Optional[QueryIntent],
    meeting_alias: str = "m",
) -> tuple:
    """
    把 QueryIntent 轉成一段可內插進 SQL 的 WHERE fragment + params。

    安全性：欄位名固定（meeting_alias.created_at / .is_confidential），所有使用者
    可控的值都走 bound params（:q_date_after / :q_date_before）→ 無 SQL injection。

    縮域策略（保守）：
      - 日期：intent.date_after / date_before 存在時才加，低風險縮域主力
      - 機密：僅在「跨會議廣泛彙整(cross_meeting) 且 include_confidential=False」時
             排除 is_confidential=TRUE 的會議，避免廣泛聚合誤帶敏感內容；
             單場 / 人物 / 待辦查詢不套用（使用者可能明確要那場）

    Returns:
        (fragment, params)
        fragment: 以 " AND ..." 開頭的字串（無條件時為空字串 ""）
        params:   dict，可直接 merge 進既有 query params
    """
    if intent is None:
        return "", {}

    clauses: List[str] = []
    params: dict = {}

    if intent.date_after:
        clauses.append(f"{meeting_alias}.created_at >= :q_date_after")
        params["q_date_after"] = intent.date_after
    if intent.date_before:
        clauses.append(f"{meeting_alias}.created_at < :q_date_before")
        params["q_date_before"] = intent.date_before

    if intent.scope == "cross_meeting" and not intent.include_confidential:
        # 排除機密會議於廣泛彙整；用 IS NOT TRUE 以相容 NULL（視為非機密）
        clauses.append(f"({meeting_alias}.is_confidential IS NOT TRUE)")

    if not clauses:
        return "", {}
    return " AND " + " AND ".join(clauses), params
