import os
import logging
import json
import re
import unicodedata
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# --- Gemini Configuration ---
# Use the same env var name as main.py
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GCP_PROJECT = os.getenv("GCP_PROJECT", "")
GCP_LOCATION = os.getenv("GCP_LOCATION", "asia-southeast1")

def get_gemini_client() -> Optional[genai.Client]:
    """Initialize and return a Gemini client."""
    try:
        if GEMINI_API_KEY:
            # Local development: use API key
            client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info(f"Gemini client initialized with API Key, model: {GEMINI_MODEL}")
            return client
        else:
            # GCP Cloud Run: use ADC via Vertex AI
            # Auto-detect project if not strictly set, but main.py sets it usually
            project = GCP_PROJECT
            if not project:
                # Try metadata server as fallback
                try:
                    import requests
                    resp = requests.get(
                        "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                        headers={"Metadata-Flavor": "Google"}, timeout=2
                    )
                    project = resp.text
                    logger.info(f"Auto-detected GCP project: {project}")
                except Exception:
                    logger.warning("Could not auto-detect GCP project")

            if project:
                client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=GCP_LOCATION
                )
                logger.info(f"Gemini client initialized with ADC (Vertex AI), project={project}")
                return client
            else:
                logger.error("No GEMINI_API_KEY and no GCP_PROJECT — cannot initialize Gemini client")
                return None
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        return None

# --- Pydantic Schemas for Structured Output ---
class GeneralSummary(BaseModel):
    summary: str
    action_items: List[str]
    decisions: List[str]
    risks: List[str]

class BANTInfo(BaseModel):
    Budget: str
    Authority: str
    Need: str
    Timeline: str

class SalesBANTSummary(BaseModel):
    summary: str
    BANT: BANTInfo
    next_steps: List[str]

class STARStory(BaseModel):
    Situation: str
    Task: str
    Action: str
    Result: str

class HRSTARSummary(BaseModel):
    candidate_summary: str
    STAR_stories: List[STARStory]
    key_strengths: List[str]

class TechnicalDecision(BaseModel):
    decision: str
    rationale: str

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

class RDSummary(BaseModel):
    summary: str
    technical_decisions: List[TechnicalDecision]
    challenges: List[Challenge]
    risks: List[Risk]
    action_items: List[ActionItem]

# Template to Schema mapping
TEMPLATE_SCHEMAS = {
    "general": GeneralSummary,
    "sales_bant": SalesBANTSummary,
    "hr_star": HRSTARSummary,
    "rd": RDSummary,
}

# --- Prompt Templates ---
class SummaryTemplate:
    def __init__(self, system_prompt: str, user_prompt_suffix: str):
        self.system_prompt = system_prompt
        self.user_prompt_suffix = user_prompt_suffix

TEMPLATES = {
    "general": SummaryTemplate(
        system_prompt="""你是專業的會議記錄助手。請根據以下會議逐字稿，生成結構化的會議摘要。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。""",
        user_prompt_suffix="請分析以下會議逐字稿並生成結構化摘要："
    ),
    "sales_bant": SummaryTemplate(
        system_prompt="""你是資深業務分析師。請根據業務會議逐字稿，運用 BANT 框架分析客戶資訊。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。""",
        user_prompt_suffix="請運用 BANT 框架分析以下業務會議："
    ),
    "hr_star": SummaryTemplate(
        system_prompt="""你是資深人資主管。請根據面試逐字稿，使用 STAR 方法評估候選人。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。""",
        user_prompt_suffix="請使用 STAR 方法分析以下面試記錄："
    ),
    "rd": SummaryTemplate(
        system_prompt="""你是資深技術專案經理。請根據研發會議逐字稿，整理技術決策與待辦事項。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。""",
        user_prompt_suffix="請整理以下研發會議的技術決策與待辦事項："
    ),
}

def clean_text(text: str) -> str:
    """Sanitize text for LLM consumption."""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\n+', '\n', text).strip()
    return text

def generate_summary(
    client: genai.Client,
    text: str,
    template_name: str = "general",
    extra_instructions: str = ""
) -> Dict[str, Any]:
    """Generate summary using Gemini API."""
    
    # Sanitize
    sanitized_text = clean_text(text)
    
    # Get template
    template = TEMPLATES.get(template_name, TEMPLATES["general"])
    
    # Build prompt
    user_prompt = f"{template.user_prompt_suffix}\n\n{sanitized_text}"
    if extra_instructions:
        user_prompt = f"【特別指令】：\n{extra_instructions}\n\n{user_prompt}"
    
    schema_class = TEMPLATE_SCHEMAS.get(template_name, GeneralSummary)
    
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{template.system_prompt}\n\n{user_prompt}",
            config={
                "response_mime_type": "application/json",
                "response_schema": schema_class, # Use direct schema class for Pydantic
                "temperature": 0.2,
                "max_output_tokens": 4096
            }
        )
        
        # In the new SDK, response.parsed is available if response_schema is set? Or response.text needs parsing?
        # The new SDK documentation says when using pydantic schema, we can get parsed object.
        # But let's stick to parsing text to be safe if .parsed isn't auto-populated in this version.
        # Actually Google GenAI SDK v1.0+ supports parsed response.
        
        try:
            # Let's try standard json load from text first to be generic
            result_json = json.loads(response.text)
            
            # Normalize output structure to match frontend expectations
            if template_name == "general":
                return result_json
            elif template_name == "sales_bant":
                return {
                    "summary": result_json.get("summary", ""),
                    "action_items": result_json.get("next_steps", []),
                    "decisions": [],
                    "risks": [],
                    "BANT": result_json.get("BANT", {}),
                    "next_steps": result_json.get("next_steps", [])
                }
            elif template_name == "hr_star":
                # Frontend expects generic keys + specific ones
                return {
                    "summary": result_json.get("candidate_summary", ""),
                    "action_items": [],
                    "decisions": [],
                    "risks": [],
                    "candidate_summary": result_json.get("candidate_summary", ""),
                    "STAR_stories": result_json.get("STAR_stories", []),
                    "key_strengths": result_json.get("key_strengths", [])
                }
            elif template_name == "rd":
                return {
                    "summary": result_json.get("summary", ""),
                    "action_items": [item.get("task", "") if isinstance(item, dict) else str(item) for item in result_json.get("action_items", [])],
                    "decisions": [d.get("decision", "") if isinstance(d, dict) else str(d) for d in result_json.get("technical_decisions", [])],
                    "risks": [r.get("risk", "") if isinstance(r, dict) else str(r) for r in result_json.get("risks", [])],
                    "technical_decisions": result_json.get("technical_decisions", []),
                    "challenges": result_json.get("challenges", [])
                }
            else:
                return result_json

        except json.JSONDecodeError:
            logger.error(f"JSON Decode Error. Raw text: {response.text}")
            return {"error": "Failed to parse JSON response", "raw_text": response.text}
            
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        return {"error": str(e)}

class PolishResult(BaseModel):
    refined: str
    translated: str

def polish_text(
    client: genai.Client,
    raw_text: str,
    source_lang: str = 'zh',
    target_lang: str = 'en'
) -> Dict[str, str]:
    """Polish text and translate using Gemini API."""
    
    prompt = f"""請幫我潤色以下文字，使其更通順自然。同時提供英文翻譯。
請以 JSON 格式回覆，包含 "refined" (潤色後的中文) 和 "translated" (英文翻譯) 兩個欄位。

原文：{raw_text}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": PolishResult,
                "temperature": 0.3
            }
        )
        
        try:
            result = json.loads(response.text)
            return {
                "polished_text": result.get("refined", raw_text),
                "refined": result.get("refined", raw_text),
                "translated": result.get("translated", "")
            }
        except json.JSONDecodeError:
            logger.error(f"Polish JSON Decode Error. Raw: {response.text}")
            return {"error": "Failed to parse JSON", "raw_text": response.text}
            
    except Exception as e:
        logger.error(f"Polish Error: {e}")
        return {"error": str(e)}
