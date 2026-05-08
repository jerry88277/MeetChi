"""
Intent classifier — 根據逐字稿內容自動判斷會議類型，回傳對應 summary template name。

Use case: 前端在使用者上傳會議後，可呼叫 /api/v1/intent/classify 取得「建議模板」
給使用者預覽，再讓 user 確認後送 generate-summary。本模組**不**自動接到 tasks
pipeline (C1 設計選擇 B：純 API 暴露，不在 background task 自動跑分類)。

Templates 對齊 apps/llm_service/app.py 內 TEMPLATES 字典：
  - general    : 預設、通用會議摘要
  - sales_bant : 業務 BANT 框架 (Budget/Authority/Need/Timeline)
  - hr_star    : 面試 STAR 框架 (Situation/Task/Action/Result)
  - rd         : 研發 (technical decisions / challenges / risks)

擴展：未來新增 template 時，必須同步：
  1. 加進 SYSTEM_TEMPLATES set
  2. 更新 CLASSIFY_PROMPT 中可選列表與描述
  3. apps/llm_service/app.py 註冊對應 schema 與 SystemPrompt

舊 template name 走 LEGACY_ALIAS 映射，避免 contract break。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ============================================
# Constants
# ============================================
DEFAULT_TEMPLATE = "general"

SYSTEM_TEMPLATES = {"general", "sales_bant", "hr_star", "rd"}

# 舊 template name → 標準名稱。增加 alias 必須在這裡 declare，避免不同
# branch / 舊 client 送的 name 直接 fallback 到 general。
LEGACY_ALIAS: dict[str, str] = {
    # 範例：若未來把 hr_star 改名 hr_interview，可加：
    # "hr_interview": "hr_star",
}

# 控制 token 成本：前段內容已足夠判斷意圖，無須整篇逐字稿
MAX_INPUT_CHARS = 4000

# 過短的逐字稿沒分類意義（如 < 200 字），直接走預設
MIN_INPUT_CHARS = 200

CLASSIFY_PROMPT = """你是會議意圖分類器。根據以下逐字稿前段，判斷此會議最匹配的摘要模板。

可選模板（必須從這 4 個選一個）：
- general    : 通用會議。部門週會、專案進度、跨團隊同步等無特定框架的會議
- sales_bant : 業務 / 銷售會議。提到客戶預算、決策權、需求、時程
- hr_star    : 面試 / 績效評估。評估候選人或員工的情境—任務—行動—結果
- rd         : 研發 / 技術會議。架構決策、bug 討論、技術風險、研發排程

只回傳純 JSON，不附其他說明，格式：
{{"template_name": "<上面 4 個之一>", "confidence": 0.0~1.0, "reason": "一句話 (10~30 字) 說明判斷理由"}}

逐字稿：
{transcript}"""


# ============================================
# Output schema
# ============================================
class IntentResult(BaseModel):
    """分類結果。任何錯誤情境也會回傳此型別 (template_name=DEFAULT_TEMPLATE, confidence=0.0)。"""

    template_name: str = Field(..., description="標準化後的 template name (一定屬於 SYSTEM_TEMPLATES)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0.0 = 預設 fallback；1.0 = 模型極確定")
    reason: str = Field(..., max_length=200, description="判斷理由 (10~30 字)")

    @field_validator("template_name")
    @classmethod
    def must_be_system_template(cls, v: str) -> str:
        if v not in SYSTEM_TEMPLATES:
            raise ValueError(f"template_name 必須屬於 {SYSTEM_TEMPLATES}, 收到 {v!r}")
        return v


# ============================================
# Public API
# ============================================
def resolve_template_name(name: Optional[str]) -> str:
    """
    把任意 template name (包含 legacy alias) 轉為系統認得的標準名稱。

    優先序：
      1. 屬於 SYSTEM_TEMPLATES → 直接回傳
      2. 屬於 LEGACY_ALIAS → 回傳對應的新名稱
      3. 其他（含 None / 空字串 / 未知） → DEFAULT_TEMPLATE
    """
    if not name:
        return DEFAULT_TEMPLATE
    if name in SYSTEM_TEMPLATES:
        return name
    if name in LEGACY_ALIAS:
        return LEGACY_ALIAS[name]
    return DEFAULT_TEMPLATE


def classify_intent(
    text: str,
    client: Any,  # google.genai.Client (避免硬 import 拖慢 module load)
    model: str = "gemini-2.5-flash-lite",
) -> IntentResult:
    """
    用 Gemini 對逐字稿做意圖分類。

    錯誤處理原則：**永不 raise**。任何 LLM API / JSON parse / schema validation
    錯誤都 fallback 到 IntentResult(template_name=DEFAULT_TEMPLATE, confidence=0.0,
    reason="<原因>")，由呼叫端決定下一步。

    Args:
        text: 完整逐字稿（自動截到 MAX_INPUT_CHARS）
        client: 已初始化的 google.genai.Client (從 app.llm_utils.get_gemini_client 取)
        model: Gemini model id；預設 flash-lite (低成本快回應)

    Returns:
        IntentResult，template_name 一定是 SYSTEM_TEMPLATES 之一

    Side effect:
        info-level log：分類成功時記 template + confidence + reason
        warning-level log：分類失敗時記原因，不阻擋回傳
    """
    # Short-circuit：太短的輸入沒判斷價值
    if not text or len(text.strip()) < MIN_INPUT_CHARS:
        return IntentResult(
            template_name=DEFAULT_TEMPLATE,
            confidence=0.0,
            reason="輸入過短，使用預設模板",
        )

    truncated = text[:MAX_INPUT_CHARS]
    prompt = CLASSIFY_PROMPT.format(transcript=truncated)

    raw_text = ""
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.1,  # 低溫求穩定可重現
                "max_output_tokens": 256,
            },
        )
        raw_text = response.text or ""
        data = json.loads(raw_text)

        # 透過 resolve_template_name 處理 unknown template
        template_name = resolve_template_name(data.get("template_name"))
        confidence = float(data.get("confidence", 0.0))
        # clamp confidence 到 [0, 1]，防止 Gemini 偶爾回傳 1.5 之類
        confidence = max(0.0, min(1.0, confidence))
        reason = str(data.get("reason", ""))[:200]

        result = IntentResult(
            template_name=template_name,
            confidence=confidence,
            reason=reason,
        )
        logger.info(
            f"[intent_classifier] classified={result.template_name} "
            f"conf={result.confidence:.2f} reason={result.reason!r}"
        )
        return result

    except json.JSONDecodeError as e:
        logger.warning(
            f"[intent_classifier] JSON parse fail: {e}; "
            f"raw={raw_text[:200]!r}"
        )
        return IntentResult(
            template_name=DEFAULT_TEMPLATE,
            confidence=0.0,
            reason="LLM 輸出非合法 JSON，fallback general",
        )
    except Exception as e:
        # 包含 API 錯誤、network、auth 等
        logger.warning(f"[intent_classifier] LLM call failed: {type(e).__name__}: {e}")
        return IntentResult(
            template_name=DEFAULT_TEMPLATE,
            confidence=0.0,
            reason=f"分類失敗 ({type(e).__name__})，fallback general",
        )
