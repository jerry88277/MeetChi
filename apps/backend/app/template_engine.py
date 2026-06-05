"""
Phase 8.2: Schema-Driven Template Engine
Replaces hardcoded TEMPLATES dict with JSON Schema-based template system.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# --- Template JSON Schema ---

class TemplateSection(BaseModel):
    """A single section within a summary template."""
    title: str = Field(..., description="段落標題，如「摘要」「待辦事項」")
    instruction: str = Field(..., description="LLM 指令，如「列出所有待辦事項」")
    output_key: str = Field(..., description="JSON output key，如「action_items」")
    output_type: str = Field("list", description="string | list | object")

class TemplateSchema(BaseModel):
    """Complete template definition."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="唯一名稱，如「general」")
    display_name: str = Field(..., description="顯示名稱，如「一般會議」")
    description: str = Field(default="")
    category: str = Field("general", description="general | sales | hr | engineering | custom")
    icon: str = Field("FileText", description="Lucide icon name")
    color: str = Field("brand-cta", description="CSS token name")
    sections: List[TemplateSection] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    is_system: bool = Field(True, description="True = 系統預設不可刪除")
    is_active: bool = Field(True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- CoT Role Inference Block (Phase 8.1.2 base + 2026-05-22 cross-chunk merge) ---
#
# 2026-05-22 改：Phase A.1 平行 ASR 把音檔切成 ~20 分鐘 chunk 各自 diarize，
# speaker label 跨 chunk 不連貫（SPEAKER_00 in chunk_0 ≠ SPEAKER_00 in chunk_1）。
# Frontend 用 SPEAKER_NN_cM 後綴標明 chunk。實測一場 2h16m 3 人會議出現
# 12 個 speaker labels（user feedback 5/22）。
#
# 修法：在這個 prompt 加「跨 chunk 同一人合併」的明確指令，要求 LLM 對所有
# SPEAKER_NN_cM 各出一筆 SpeakerRole，但「實際同一人」共用同一個 display_name。
# 既有 frontend SpeakerName 已用 display_name 渲染，不必改前端。
COT_ROLE_INFERENCE_BLOCK = """
## 步驟一：角色推斷 + 跨 chunk 講者合併 (Chain-of-Thought)

本系統把長音檔切成多段（chunk）分別 diarize，每段 chunk 內的 speaker 編號
**獨立**，不跨段一致。例如：
  - `SPEAKER_00_c0`（chunk 0 的講者 0）
  - `SPEAKER_00_c1`（chunk 1 的講者 0，可能是另一個人）
  - `SPEAKER_01_c1`（chunk 1 的講者 1）

你的任務：在逐字稿中找出**所有不同的 SPEAKER_NN_cM 標籤**，根據以下線索
判斷哪些其實是「同一個自然人」：
  1. **內容延續性**：跨 chunk 邊界附近，如果語氣 / 用詞 / 主題連續，通常是同一人
  2. **角色語氣**：主持人 vs 客戶 vs 講者通常用詞差異顯著
  3. **稱呼**：講者被他人稱呼為「王總編輯」「簡博士」等明確 ID，記入
  4. **發言比例**：若某 `_cM` chunk 內某 SPEAKER 發言極多（如主持人/keynote
     講者），對應到其他 chunk 內發言量類似的 SPEAKER 機率高

輸出 `speaker_roles`：對逐字稿中**每一個唯一的 SPEAKER_NN_cM**都出一筆：
  - speaker_id: 原始標籤（如 "SPEAKER_00_c0"）
  - display_name: 最可能的稱呼。**同一個人**的多個 chunk 標籤共用**完全相同**
    的 display_name（這是合併的關鍵；前端會用 display_name 歸併）
  - role: 角色分類（如「主持人」、「客戶」、「講者」、「面試者」）。若同一人
    在不同段扮演不同角色（例如主持人也提問），用**主要**角色

## 步驟二：基於角色生成摘要

在了解每位說話者的角色後，生成摘要時：
  - 引言 (key_quotes) 仍寫原始 SPEAKER_NN_cM 標籤（前端會用 mapping 渲染）
  - 摘要敘述用 display_name（如「王總編輯指出」而非「Speaker_0 指出」）
"""


# --- 10 System Templates ---

SYSTEM_TEMPLATES: List[TemplateSchema] = [
    # 1. General
    TemplateSchema(
        id="tpl-general",
        name="general",
        display_name="一般會議",
        description="通用模板，含摘要、待辦、決議與風險",
        category="general",
        icon="FileText",
        color="brand-cta",
        sections=[
            TemplateSection(title="摘要", instruction="綜合整理會議重點，以段落呈現", output_key="summary", output_type="string"),
            TemplateSection(title="待辦事項", instruction="列出所有明確的待辦事項", output_key="action_items", output_type="list"),
            TemplateSection(title="決議", instruction="列出會議中確定的決議", output_key="decisions", output_type="list"),
            TemplateSection(title="風險", instruction="列出可能的風險或未解決問題", output_key="risks", output_type="list"),
        ],
        tags=["摘要", "待辦事項", "決議"],
    ),
    # 2. Sales BANT
    TemplateSchema(
        id="tpl-sales-bant",
        name="sales_bant",
        display_name="業務會議 (BANT)",
        description="Budget / Authority / Need / Timeline 分析",
        category="sales",
        icon="DollarSign",
        color="status-warning",
        sections=[
            TemplateSection(title="摘要", instruction="整理業務會議內容", output_key="summary", output_type="string"),
            TemplateSection(title="BANT 分析", instruction="用 BANT 架構（Budget/Authority/Need/Timeline）分析客戶資訊", output_key="BANT", output_type="object"),
            TemplateSection(title="後續步驟", instruction="列出後續行動計畫", output_key="next_steps", output_type="list"),
        ],
        tags=["預算", "決策者", "需求", "時程"],
    ),
    # 3. HR STAR
    TemplateSchema(
        id="tpl-hr-star",
        name="hr_star",
        display_name="面試評估 (STAR)",
        description="Situation / Task / Action / Result 面試分析",
        category="hr",
        icon="Users",
        color="status-success",
        sections=[
            TemplateSection(title="候選人摘要", instruction="綜合評估候選人表現", output_key="candidate_summary", output_type="string"),
            TemplateSection(title="STAR 故事", instruction="用 STAR 方法（Situation/Task/Action/Result）整理候選人描述的經歷", output_key="STAR_stories", output_type="list"),
            TemplateSection(title="核心優勢", instruction="列出候選人展現的核心優勢", output_key="key_strengths", output_type="list"),
        ],
        tags=["情境", "任務", "行動", "結果"],
    ),
    # 4. R&D
    TemplateSchema(
        id="tpl-rd",
        name="rd",
        display_name="研發會議",
        description="技術決策與進度追蹤",
        category="engineering",
        icon="Code",
        color="brand-accent",
        sections=[
            TemplateSection(title="摘要", instruction="整理研發會議重點", output_key="summary", output_type="string"),
            TemplateSection(title="技術決策", instruction="列出會議中做出的技術決策及理由", output_key="technical_decisions", output_type="list"),
            TemplateSection(title="挑戰", instruction="列出目前面臨的挑戰及建議解法", output_key="challenges", output_type="list"),
            TemplateSection(title="風險", instruction="列出技術風險及緩解措施", output_key="risks", output_type="list"),
            TemplateSection(title="待辦事項", instruction="列出具體待辦事項、負責人及期限", output_key="action_items", output_type="list"),
        ],
        tags=["技術決策", "進度", "風險"],
    ),
    # 5. Project Review (NEW)
    TemplateSchema(
        id="tpl-project-review",
        name="project_review",
        display_name="專案進度追蹤",
        description="專案里程碑、進度與阻塞點追蹤",
        category="general",
        icon="Target",
        color="brand-cta",
        sections=[
            TemplateSection(title="專案狀態摘要", instruction="整理專案目前整體進度", output_key="summary", output_type="string"),
            TemplateSection(title="里程碑進度", instruction="列出各里程碑的完成狀態", output_key="milestones", output_type="list"),
            TemplateSection(title="阻塞點", instruction="列出目前的阻塞點和瓶頸", output_key="blockers", output_type="list"),
            TemplateSection(title="待辦事項", instruction="列出下一步行動計畫", output_key="action_items", output_type="list"),
        ],
        tags=["里程碑", "進度", "阻塞"],
    ),
    # 6. Brainstorm (NEW)
    TemplateSchema(
        id="tpl-brainstorm",
        name="brainstorm",
        display_name="腦力激盪",
        description="創意發想與點子整理",
        category="general",
        icon="Lightbulb",
        color="status-warning",
        sections=[
            TemplateSection(title="主題摘要", instruction="整理討論主題和背景", output_key="summary", output_type="string"),
            TemplateSection(title="點子清單", instruction="列出所有被提出的點子或方案", output_key="ideas", output_type="list"),
            TemplateSection(title="優先候選", instruction="根據討論共識，列出最受支持的方案", output_key="top_picks", output_type="list"),
            TemplateSection(title="後續行動", instruction="列出需要進一步驗證或執行的行動", output_key="action_items", output_type="list"),
        ],
        tags=["創意", "發想", "方案"],
    ),
    # 7. Daily Standup (NEW)
    TemplateSchema(
        id="tpl-standup",
        name="standup",
        display_name="每日站會",
        description="Yesterday / Today / Blockers 三段式報告",
        category="engineering",
        icon="Clock",
        color="brand-accent",
        sections=[
            TemplateSection(title="摘要", instruction="簡要整理今日站會內容", output_key="summary", output_type="string"),
            TemplateSection(title="昨日完成", instruction="整理每位成員昨日完成的工作", output_key="yesterday", output_type="list"),
            TemplateSection(title="今日計畫", instruction="整理每位成員今日的工作計畫", output_key="today", output_type="list"),
            TemplateSection(title="阻塞點", instruction="列出任何需要協助的阻塞點", output_key="blockers", output_type="list"),
        ],
        tags=["站會", "進度", "阻塞"],
    ),
    # 8. Sprint Retrospective (NEW)
    TemplateSchema(
        id="tpl-retrospective",
        name="retrospective",
        display_name="Sprint 回顧",
        description="做得好 / 待改善 / 行動計畫",
        category="engineering",
        icon="RotateCcw",
        color="status-success",
        sections=[
            TemplateSection(title="Sprint 摘要", instruction="整理本次 Sprint 的整體表現", output_key="summary", output_type="string"),
            TemplateSection(title="做得好的地方", instruction="列出團隊做得好的方面", output_key="went_well", output_type="list"),
            TemplateSection(title="待改善的地方", instruction="列出需改進的方面", output_key="to_improve", output_type="list"),
            TemplateSection(title="改善行動", instruction="列出具體的改善行動計畫", output_key="action_items", output_type="list"),
        ],
        tags=["回顧", "改善", "Sprint"],
    ),
    # 9. Client Requirements (NEW)
    TemplateSchema(
        id="tpl-client-requirements",
        name="client_requirements",
        display_name="需求訪談",
        description="客戶需求蒐集與優先排序",
        category="sales",
        icon="ClipboardList",
        color="status-warning",
        sections=[
            TemplateSection(title="訪談摘要", instruction="整理需求訪談的背景和目的", output_key="summary", output_type="string"),
            TemplateSection(title="需求清單", instruction="列出客戶提出的所有需求，標示優先程度（高/中/低）", output_key="requirements", output_type="list"),
            TemplateSection(title="限制條件", instruction="列出技術或商業限制", output_key="constraints", output_type="list"),
            TemplateSection(title="後續步驟", instruction="列出後續確認事項和行動計畫", output_key="action_items", output_type="list"),
        ],
        tags=["需求", "訪談", "優先序"],
    ),
    # 10. Training (NEW)
    TemplateSchema(
        id="tpl-training",
        name="training",
        display_name="教育訓練",
        description="課程重點摘要與學習要點",
        category="general",
        icon="GraduationCap",
        color="brand-cta",
        sections=[
            TemplateSection(title="課程摘要", instruction="整理課程主題和重點", output_key="summary", output_type="string"),
            TemplateSection(title="學習要點", instruction="列出核心學習要點和概念", output_key="key_learnings", output_type="list"),
            TemplateSection(title="Q&A 摘要", instruction="整理提問與解答", output_key="qa_summary", output_type="list"),
            TemplateSection(title="延伸學習", instruction="列出推薦的延伸閱讀或練習", output_key="further_reading", output_type="list"),
        ],
        tags=["課程", "學習", "Q&A"],
    ),
]

# Quick lookup by name
_TEMPLATE_BY_NAME: Dict[str, TemplateSchema] = {t.name: t for t in SYSTEM_TEMPLATES}


def get_template_by_name(name: str) -> Optional[TemplateSchema]:
    """Get a system template by name."""
    return _TEMPLATE_BY_NAME.get(name)


def get_all_system_templates() -> List[TemplateSchema]:
    """Return all system templates."""
    return SYSTEM_TEMPLATES


# ============================================
# 摘要規格 V2 (SUMMARY_FINAL_SPEC.md, 2026-05-11)
# Q1+Q2 章節 + 時序子段；Q3 結論視情況才列；Q4 引言要帶 time；Q7 三個新欄位
# ============================================
SUMMARY_V2_REQUIREMENTS = """
## 摘要規格 V2 — 新增結構化欄位

除了既有的 summary/decisions/risks 等，以下欄位**必須**輸出：

### 1. tldr (100-150 字)
一句話結論，讓使用者讀完就 grab 全會議 30-40% 重點。BLUF 原則（Bottom Line Up Front）：
最重要的決策/結論/警訊放在第一句。

### 2. chapters (6-10 個主題章節，按議題聚類**非時序**)
不要按發言順序切，要按「主題」分。每章節：
- title: 主題名稱（不是流水號）
- summary: 100-150 字摘要
- bullets: 3-5 條重點，每條 20-30 字
- key_quotes: 0-2 條原音引言，含 time（秒數）
- sub_chapters: 該主題在逐字稿中對應的時序子段（按發言時間排序，30-90 秒一段）：
  - **每章節 sub_chapters 上限 4 條**（即使主題很長也不能超過；挑最有資訊
    密度的時段，其餘略過）
  - time_start / time_end: 秒
  - summary: 30-50 字
  - bullets: 2-3 條
  - key_quotes: 0-1 條（極關鍵才列）

### 3. speaker_contributions (與會者貢獻度)
每位講者一筆：
- speaker: SPEAKER_xx
- role: 主持人 / 講者 / 客戶 ...
- speak_time_pct: 0-100，發言時長占比（估算）
- main_topics: 該講者主導的 2-4 個議題
- key_contribution: 一句話描述貢獻

### 4. next_steps (會議**之後**該追蹤的事項；與 action_items 區隔)
action_items 是會議中當下決定的待辦；next_steps 是會議之後的後續追蹤。
每筆：
- task: 任務描述
- assignee: 負責人（可空）
- due: ISO date "YYYY-MM-DD"（可空）
- follow_up_meeting: 若需開後續會議的提示（可空）

### 5. 引言（key_quotes）規範
- 每條引言 **必須含 time**（從原始逐字稿的時間區間取首秒）
- speaker 保留 SPEAKER_xx 格式（前端會 transform 為 display_name）
- 文字 ≤ 150 字，逐字保留不潤稿

### 6. 結論三欄（decisions / risks / action_items）— 視情況才列
- 若會議**明確**討論決策/風險/待辦，才列出
- 若會議性質不涉及（如純講座、分享會），decisions/risks 可空陣列
- **嚴禁瞎掰**強行湊條目，會稀釋資訊價值

### 7. cross_meeting_refs
**不要 LLM 生成此欄位**。Backend 會在 summary 產生後自己用 pgvector 查補。
"""


def build_prompt_from_template(
    template: TemplateSchema,
    transcript: str,
    user_instruction: str = "",
) -> tuple:
    """Build system_prompt and user_prompt from a TemplateSchema.

    Returns (system_prompt, user_prompt_suffix) tuple.

    2026-05-13 (feedback 3a4b81b4)：長會議 (>= ~50K chars transcript) Gemini
    response 即使 max_output_tokens=65535 仍會截斷 (數位時代 2h16m 實測 hit
    MAX_TOKENS, response 129989 chars → JSON parse fail)。

    Root cause：V2 schema chapters × sub_chapters × bullets × quotes 對長
    逐字稿展開後過於詳細。65535 是 Gemini API 硬上限，加不了。

    修法：transcript 超過 50K 字（約 1.5h+ 中文會議）→ 注入「精簡指令」
    要求 LLM 縮減 chapter 數與 sub_chapter 數，控制 response 在硬上限內。
    """
    # 動態長度適配 (50K chars ~ Gemini 25K-30K input tokens for zh)
    transcript_len = len(transcript)
    long_meeting_addendum = ""
    if transcript_len >= 50_000:
        long_meeting_addendum = (
            "\n## ⚠️ 本會議較長之精簡規則（必須遵守）\n"
            f"原始逐字稿長度 {transcript_len:,} 字（屬長會議）。為避免回應超過 "
            "API 硬上限 (65K tokens)，請**強制執行**以下精簡規則：\n"
            "  - chapters：**最多 6 個**（從 6-10 上限再壓縮）\n"
            "  - 每章節 sub_chapters：**最多 3 條**（從 4 條再壓縮）\n"
            "  - bullets：每處最多 3 條（從 3-5 上限壓縮）\n"
            "  - key_quotes：每章節最多 1 條（從 0-2 壓縮）；sub_chapter 不放 quote\n"
            "  - summary 字數可保持原規格，但勿超過\n"
            "**這是長會議避免截斷的硬性限制**。你寧可少列重點也不能截斷 JSON。"
        )

    # Build section instructions
    section_instructions = "\n".join(
        f"- **{s.title}** (output_key: `{s.output_key}`, type: {s.output_type}): {s.instruction}"
        for s in template.sections
    )

    system_prompt = f"""你是專業的會議記錄助手。請根據以下會議逐字稿，生成結構化的會議摘要。
請使用繁體中文撰寫回應，並以 JSON 格式輸出。
注意：逐字稿中 SPEAKER_NN_cM 為說話者標籤（音檔分段後的 diarization ID），
摘要描述請使用「說話者 A」/「說話者 B」等通稱，或根據內容推斷的角色名稱。

## 模板原有段落要求
以下是模板「{template.display_name}」要求的 JSON 欄位：
{section_instructions}

{SUMMARY_V2_REQUIREMENTS}
{long_meeting_addendum}

請確保輸出的 JSON 包含所有上述欄位（模板原欄位 + V2 結構化欄位）。
"""

    user_prompt_suffix = (
        f"請分析以下會議逐字稿並生成結構化摘要（模板：{template.display_name}）。"
        "務必輸出 chapters / speaker_contributions / next_steps / 含 time 的 key_quotes 等 V2 欄位。"
    )

    return system_prompt, user_prompt_suffix


def build_schema_from_template(template: TemplateSchema) -> Dict[str, Any]:
    """Build a JSON schema dict from a TemplateSchema for Gemini structured output.
    
    Returns a dict that can be used as response_schema in Gemini API.
    """
    from pydantic import create_model
    from typing import Optional, List as TypingList
    
    # Import SpeakerRole from existing code
    from app.llm_utils import SpeakerRole
    
    # Build dynamic fields — speaker_roles excluded from main summary call;
    # handled by infer_speaker_roles() in tasks.py (2026-06-03 MAX_TOKENS fix)
    fields = {}
    
    type_mapping = {
        "string": (str, ...),
        "list": (TypingList[str], []),
        "object": (Dict[str, str], {}),
    }
    
    for section in template.sections:
        fields[section.output_key] = type_mapping.get(section.output_type, (str, ...))
    
    DynamicSchema = create_model(f"{template.name.title()}Summary", **fields)
    return DynamicSchema
