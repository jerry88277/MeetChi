"""
Intent classification API endpoint.

  POST /api/v1/intent/classify
    body:     {"text": "<逐字稿純文字>"}
    response: {"template_name": str, "confidence": float, "reason": str}

設計選擇 (C1=B 純 API)：本 router 只做「給逐字稿，回建議模板」的純 stateless
查詢；**不**自動接到 background task pipeline。前端可在使用者上傳會議後預覽
模板建議，或在 dashboard 點按鈕重算建議。

降級行為：分類失敗時回傳 template_name="general"、confidence=0.0；不會 5xx。
唯一會 5xx 的情境是 Gemini client 本身無法初始化 (503)。
"""

import logging

from fastapi import APIRouter, HTTPException

from app.intent_classifier import IntentResult, classify_intent
from app.llm_utils import get_gemini_client
from app.schemas import IntentClassifyRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/api/v1/intent/classify",
    response_model=IntentResult,
    tags=["Intent"],
)
async def classify(request: IntentClassifyRequest) -> IntentResult:
    """根據逐字稿內容回傳建議的 summary template。

    Returns:
        IntentResult: 即使分類失敗也會回傳合法物件 (template=general,
        confidence=0.0, reason 為錯誤摘要)。
    Raises:
        HTTPException 503: Gemini client 不可用 (環境變數沒設 GEMINI_API_KEY
        或 GCP_PROJECT)。
    """
    client = get_gemini_client()
    if client is None:
        logger.error("[intent.classify] Gemini client unavailable")
        raise HTTPException(status_code=503, detail="Gemini client unavailable")

    return classify_intent(request.text, client)
