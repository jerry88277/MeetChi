"""
MeetChi LLM Service - Gemini API Only
Lightweight Flask API for meeting summarization using Google Gemini.
"""

import json
import os
import re
import logging
import unicodedata
from typing import List, Optional
from flask import Flask, request, jsonify
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Gemini API Configuration ---
USE_GEMINI = os.getenv("USE_GEMINI", "true").lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite-preview-06-17")
MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"
GCP_PROJECT = os.getenv("GCP_PROJECT", "")
GCP_LOCATION = os.getenv("GCP_LOCATION", "asia-southeast1")

print(f"USE_GEMINI:{USE_GEMINI}, GEMINI_MODEL:{GEMINI_MODEL}, MOCK_LLM:{MOCK_LLM}")

# Initialize Gemini client
# Priority: API Key (local dev) > ADC via Vertex AI (Cloud Run Service Account)
gemini_client = None
if USE_GEMINI:
    try:
        from google import genai
        if GEMINI_API_KEY:
            # Local development: use API key from .env
            gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info(f"Gemini client initialized with API Key, model: {GEMINI_MODEL}")
        else:
            # GCP Cloud Run: use ADC via Vertex AI backend
            # Auto-detect project from metadata server if not set
            project = GCP_PROJECT
            if not project:
                try:
                    import requests as _req
                    resp = _req.get(
                        "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                        headers={"Metadata-Flavor": "Google"}, timeout=2
                    )
                    project = resp.text
                    logger.info(f"Auto-detected GCP project: {project}")
                except Exception:
                    logger.warning("Could not auto-detect GCP project from metadata server")

            if project:
                gemini_client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=GCP_LOCATION
                )
                logger.info(f"Gemini client initialized with ADC (Vertex AI), project={project}, location={GCP_LOCATION}, model: {GEMINI_MODEL}")
            else:
                logger.error("No GEMINI_API_KEY and no GCP_PROJECT — cannot initialize Gemini client")
    except ImportError:
        logger.error("google-genai not installed!")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")

# --- Pydantic Schemas for Structured Output ---
# 模板改善 A (uplift)：對齊 HackMD-style 設計原則
#   1. TL;DR (tldr) 100-200 字結論先行，避免「太短」與「流水帳」兩種失敗模式
#   2. 強制保留 1-3 條原音引言 (key_quotes)
#   3. 各 list 控制 max_length，避免 LLM 塞流水帳
#   4. 加上重要度 / 評分 / 信心度等量化欄位，讓 user 一眼看密度

class KeyQuote(BaseModel):
    """A single original-audio quote, preserved verbatim with speaker label."""
    speaker: str  # e.g. "SPEAKER_00" or 真人姓名
    text: str  # 原音引言，不改寫，≤ 150 字


class GeneralSummary(BaseModel):
    tldr: str  # 100-200 字白話結論先行 (新增)
    summary: str  # 600 字以內結構化摘要
    action_items: List[str]  # 每條 ≤ 50 字
    decisions: List[str]  # 每條 ≤ 50 字
    risks: List[str]  # 每條 ≤ 50 字
    key_quotes: List[KeyQuote] = []  # 1-3 條原音引言 (新增)

class BANTInfo(BaseModel):
    """每個欄位含內容 + 信心度 + 證據引言"""
    value: str  # ≤ 80 字 (新增 sub-structure)
    confidence: str  # "high" | "medium" | "low" (新增)
    evidence_quote: Optional[str] = None  # 原音引用（若逐字稿有）(新增)

class BANTBlock(BaseModel):
    Budget: BANTInfo
    Authority: BANTInfo
    Need: BANTInfo
    Timeline: BANTInfo

class SalesBANTSummary(BaseModel):
    tldr: str  # 100-200 字 (新增)
    summary: str
    BANT: BANTBlock  # 升級為 sub-object 結構
    next_steps: List[str]
    deal_signal: str = "warm"  # "hot" | "warm" | "cold" (新增)
    objections: List[str] = []  # 客戶提出的反對意見，常被忽略 (新增)
    key_quotes: List[KeyQuote] = []

class STARStory(BaseModel):
    Situation: str
    Task: str
    Action: str
    Result: str
    competency_tag: Optional[str] = None  # 對應職能標籤 (新增)
    impact_score: Optional[int] = None  # 1-5 (新增)
    quote: Optional[str] = None  # 候選人原話 (新增)

class HRSTARSummary(BaseModel):
    tldr: str  # 100-200 字 (新增)
    candidate_summary: str
    STAR_stories: List[STARStory]
    key_strengths: List[str]
    red_flags: List[str] = []  # ⚠️ 強制思考過 (新增)
    fit_score: Optional[int] = None  # 1-5 整體匹配度 (新增)
    key_quotes: List[KeyQuote] = []

class TechnicalDecision(BaseModel):
    decision: str
    rationale: str
    priority: str = "P2"  # "P0" | "P1" | "P2" (新增)
    blocking: bool = False  # 是否阻擋其他項 (新增)

class Challenge(BaseModel):
    challenge: str
    proposed_solution: str

class Risk(BaseModel):
    risk: str
    mitigation: str

class ActionItem(BaseModel):
    task: str
    owner: Optional[str] = None
    deadline: Optional[str] = None
    dependencies: List[str] = []  # 依賴哪些前置 task (新增)

class RDSummary(BaseModel):
    tldr: str  # 100-200 字 (新增)
    summary: str
    technical_decisions: List[TechnicalDecision]
    challenges: List[Challenge]
    risks: List[Risk]
    action_items: List[ActionItem]
    key_quotes: List[KeyQuote] = []

# Template to Schema mapping
TEMPLATE_SCHEMAS = {
    "general": GeneralSummary,
    "sales_bant": SalesBANTSummary,
    "hr_star": HRSTARSummary,
    "rd": RDSummary,
}

# --- Template Definitions ---
class SummaryTemplate:
    def __init__(self, system_prompt: str, user_prompt_suffix: str):
        self.system_prompt = system_prompt
        self.user_prompt_suffix = user_prompt_suffix

# 寫作紀律 — 4 個模板共用，注入到 system_prompt 開頭
# 對應 HackMD podcast 範本的金字塔原則 + 反流水帳設計
WRITING_DISCIPLINE = """【寫作紀律 — 必須嚴格遵守】
1. 【金字塔原則】先寫結論再寫細節。tldr 欄位是「給沒時間看完整摘要的主管 30 秒讀完」，
   100-200 字白話結論，不要寫「會議討論了 X」這種空話，必須有具體決策/數字/結果。
2. 【反流水帳】禁止「A 說 X，B 回 Y，A 又補充 Z」逐句復述。提煉重點，不要復述對話。
3. 【字數控制】每個 list 的 bullet ≤ 50 字；每個 str 欄位除非註明否則 ≤ 200 字。
   超過字數的內容請拆解或濃縮，不要硬塞。
4. 【強制原音引言】key_quotes 至少 1 條、最多 3 條，原文不改寫，標 speaker。
   引言要有資訊量（含具體數字、決策、轉折），不要選寒暄與場面話。
5. 【誠實拒答】找不到資訊的欄位填 "(逐字稿未提及)"，**禁止編造**。
   list 類型若無資訊填空 list []，**禁止**強行湊數。
6. 【重要度標記】list 內元素若有顯著重要度差異，前綴 🔑（核心）/ ⚡（急迫）/ ⚠️（風險）。
7. 【純文字輸出】禁止 ** / # / * / > 等 markdown 符號，僅可用 \\n 換行。
"""

TEMPLATES = {
    "general": SummaryTemplate(
        system_prompt=f"""你是專業的會議記錄助手。請根據以下會議逐字稿，生成結構化的會議摘要。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。

{WRITING_DISCIPLINE}

【模板特定要求】
- tldr 必須包含「會議產出了什麼」（決議/結論/下一步），而非「討論了什麼話題」
- decisions 是「已決定」的事；待決定事項放 risks 或 action_items
- action_items 含負責人（若可從逐字稿推斷）
""",
        user_prompt_suffix="請分析以下會議逐字稿並生成結構化摘要："
    ),
    "sales_bant": SummaryTemplate(
        system_prompt=f"""你是資深業務分析師。請根據業務會議逐字稿，運用 BANT 框架分析客戶資訊。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。

{WRITING_DISCIPLINE}

【模板特定要求】
- BANT 4 項各 80 字內描述客戶實際說了什麼，不是你的推論
- BANT 每項附 confidence（high/medium/low）與 evidence_quote（原音引言，若有）
- deal_signal: hot（高意向、明確時程）/ warm（有預算需求但無 deadline）/ cold（探索）
- objections: 客戶提出的反對意見、價格抗拒、競品比較等——這欄常被忽略但是 deal close 關鍵
""",
        user_prompt_suffix="請運用 BANT 框架分析以下業務會議："
    ),
    "hr_star": SummaryTemplate(
        system_prompt=f"""你是資深人資主管。請根據面試逐字稿，使用 STAR 方法評估候選人。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。

{WRITING_DISCIPLINE}

【模板特定要求】
- STAR_stories 每個故事附 competency_tag（對應職能：問題解決 / 溝通 / 領導 / 技術深度 等）
- impact_score 1-5：1=陳述案例 / 3=有量化結果 / 5=有規模/成本/時間多維度量化
- quote: 候選人原話（評委可作為紀錄供 follow-up 確認）
- red_flags: 觀察到的疑慮/不一致/迴避（**強制思考過**，無則填 []）
- fit_score 1-5: 候選人 vs 該職位整體匹配度
""",
        user_prompt_suffix="請使用 STAR 方法分析以下面試記錄："
    ),
    "rd": SummaryTemplate(
        system_prompt=f"""你是資深技術專案經理。請根據研發會議逐字稿，整理技術決策與待辦事項。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。

{WRITING_DISCIPLINE}

【模板特定要求】
- technical_decisions 每項附 priority（P0 阻擋上線 / P1 本週要 / P2 規劃中）與 blocking（是否阻擋其他項）
- challenges 是「目前卡住的技術問題」，含 proposed_solution（會議產出的解法，若無則 "(逐字稿未提及)"）
- risks 是「未來可能爆的問題」（區別於 challenges）
- action_items 含 dependencies（依賴哪些前置 task）以避免併行衝突
""",
        user_prompt_suffix="請整理以下研發會議的技術決策與待辦事項："
    ),
}

def get_template(template_name: str) -> SummaryTemplate:
    return TEMPLATES.get(template_name, TEMPLATES["general"])

# --- Health Check Endpoint ---
@app.route('/health', methods=['GET'])
def health_check():
    gemini_available = gemini_client is not None
    auth_mode = "api_key" if GEMINI_API_KEY else "adc"
    return jsonify({
        "status": "ready",
        "gemini_enabled": gemini_available,
        "gemini_model": GEMINI_MODEL if gemini_available else None,
        "auth_mode": auth_mode if gemini_available else None,
        "mock_mode": MOCK_LLM,
        "version": "2.1.0-adc"
    }), 200

# --- Polish Endpoint (Gemini-based) ---
@app.route('/polish', methods=['POST'])
def polish_text():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400
    
    raw_text = data['text']
    source_lang = data.get('source_lang', 'zh')
    target_lang = data.get('target_lang', 'en')

    if MOCK_LLM:
        return jsonify({
            "polished_text": f"[Mock Polished] {raw_text}",
            "refined": raw_text,
            "translated": f"[Mock Translation] {raw_text[:50]}..."
        })

    if not gemini_client:
        return jsonify({"error": "Gemini client not available"}), 503

    try:
        prompt = f"""請幫我潤色以下文字，使其更通順自然。同時提供英文翻譯。
請以 JSON 格式回覆，包含 "refined" (潤色後的中文) 和 "translated" (英文翻譯) 兩個欄位。

原文：{raw_text}"""

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.3
            }
        )
        
        result = json.loads(response.text)
        return jsonify({
            "polished_text": result.get("refined", raw_text),
            "refined": result.get("refined", raw_text),
            "translated": result.get("translated", "")
        })

    except Exception as e:
        logger.error(f"Polish error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --- Summarize Endpoint ---
@app.route('/summarize', methods=['POST'])
def summarize_meeting():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400
    
    raw_transcript = data['text']
    template_name = data.get('template_name', 'general')
    extra_instructions = data.get('extra_instructions', '')

    # --- MOCK MODE ---
    if MOCK_LLM:
        logger.info(f"[MOCK] Summarizing with template: {template_name}")
        return jsonify({
            "summary": f"[Mock Summary for {template_name}] {raw_transcript[:100]}...",
            "action_items": ["Mock Action 1", "Mock Action 2"],
            "decisions": ["Mock Decision 1"],
            "risks": []
        })

    # --- Check Gemini availability ---
    if not gemini_client:
        return jsonify({
            "summary": "Gemini API 未設定，無法生成摘要。",
            "action_items": [],
            "decisions": [],
            "risks": [],
            "error": "Gemini client not available"
        }), 503

    # --- Sanitization ---
    sanitized_text = unicodedata.normalize('NFKC', raw_transcript)
    sanitized_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', sanitized_text)
    sanitized_text = re.sub(r'\n+', '\n', sanitized_text).strip()

    # Get template
    template = get_template(template_name)
    
    # Build prompt
    user_prompt = f"{template.user_prompt_suffix}\n\n{sanitized_text}"
    if extra_instructions:
        user_prompt = f"【特別指令】：\n{extra_instructions}\n\n{user_prompt}"

    # --- GEMINI API CALL ---
    try:
        schema_class = TEMPLATE_SCHEMAS.get(template_name, GeneralSummary)
        
        logger.info(f"[Gemini] Summarizing with template: {template_name}, model: {GEMINI_MODEL}")
        
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{template.system_prompt}\n\n{user_prompt}",
            config={
                "response_mime_type": "application/json",
                "response_json_schema": schema_class.model_json_schema(),
                "temperature": 0.2,
                "max_output_tokens": 4096
            }
        )
        
        result_text = response.text
        logger.info(f"[Gemini] Raw response: {result_text[:500]}...")
        
        # Parse JSON response
        try:
            result_json = json.loads(result_text)
            
            # Normalize output for general template compatibility
            if template_name == "general":
                return jsonify(result_json)
            elif template_name == "sales_bant":
                return jsonify({
                    "summary": result_json.get("summary", ""),
                    "action_items": result_json.get("next_steps", []),
                    "decisions": [],
                    "risks": [],
                    "BANT": result_json.get("BANT", {}),
                    "next_steps": result_json.get("next_steps", [])
                })
            elif template_name == "hr_star":
                return jsonify({
                    "summary": result_json.get("candidate_summary", ""),
                    "action_items": [],
                    "decisions": [],
                    "risks": [],
                    "candidate_summary": result_json.get("candidate_summary", ""),
                    "STAR_stories": result_json.get("STAR_stories", []),
                    "key_strengths": result_json.get("key_strengths", [])
                })
            elif template_name == "rd":
                return jsonify({
                    "summary": result_json.get("summary", ""),
                    "action_items": [item.get("task", "") for item in result_json.get("action_items", [])],
                    "decisions": [d.get("decision", "") for d in result_json.get("technical_decisions", [])],
                    "risks": [r.get("risk", "") for r in result_json.get("risks", [])],
                    "technical_decisions": result_json.get("technical_decisions", []),
                    "challenges": result_json.get("challenges", [])
                })
            else:
                return jsonify(result_json)
                
        except json.JSONDecodeError as e:
            logger.error(f"[Gemini] Failed to parse JSON: {e}. Raw: {result_text}")
            return jsonify({
                "summary": result_text,
                "action_items": [],
                "decisions": [],
                "risks": [],
                "error": "JSON parsing failed"
            })
            
    except Exception as e:
        logger.error(f"[Gemini] Error: {e}", exc_info=True)
        return jsonify({
            "summary": f"摘要生成失敗：{str(e)}",
            "action_items": [],
            "decisions": [],
            "risks": [],
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)