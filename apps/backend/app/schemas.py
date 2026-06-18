"""
Pydantic API schemas — request/response models for FastAPI routes.

Extracted from main.py to keep route files schema-aware without
re-importing from a 1.8k-line module.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================
# Transcript Segment
# ============================================
class TranscriptSegmentRead(BaseModel):
    id: str
    order: int
    start_time: float
    end_time: float
    speaker: Optional[str]
    content_raw: str
    content_polished: Optional[str]
    content_translated: Optional[str]
    is_final: bool

    class Config:
        from_attributes = True


class TranscriptSegmentCreate(BaseModel):
    id: Optional[str] = None
    order: int
    start_time: float
    end_time: float
    speaker: Optional[str] = None
    content_raw: str
    content_polished: Optional[str] = None
    content_translated: Optional[str] = None
    is_final: bool


# ============================================
# Meeting
# ============================================
class MeetingRead(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    duration: Optional[float]
    audio_url: Optional[str]
    language: str = "zh"
    template_name: str = "general"
    transcript_raw: Optional[str]
    transcript_polished: Optional[str]
    summary_json: Optional[str]
    speaker_mappings: Optional[str] = None  # Phase 8.1.3
    completed_at: Optional[datetime] = None  # Processing completion timestamp
    is_confidential: bool = False  # Sprint 2e Phase 1 (2026-05-11)
    failure_reason: Optional[str] = None  # 2026-05-25 (Y7)：給 FAILED meeting 顯示具體原因
    processing_stage: Optional[str] = None  # queued | transcribing | summarizing

    transcript_segments: List[TranscriptSegmentRead] = []  # Include segments for detail view

    class Config:
        from_attributes = True


# 輕量化版本給 list endpoint：
#   排除 transcript_segments / transcript_raw / transcript_polished 三個重欄位
#   原本 list 一個 2.3 小時會議要拉幾千 segments lazy-load N+1，造成 worker block
#   保留 summary_json 給 MeetingCard 顯示決策/待辦/風險計數
class MeetingListItem(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    duration: Optional[float]
    audio_url: Optional[str]
    language: str = "zh"
    template_name: str = "general"
    summary_json: Optional[str]
    speaker_mappings: Optional[str] = None
    is_confidential: bool = False  # Sprint 2e Phase 1：list 也要看得到 badge
    processing_stage: Optional[str] = None  # queued | transcribing | summarizing

    class Config:
        from_attributes = True


class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    language: str = Field("zh", min_length=2, max_length=10)
    template_name: str = Field("general", min_length=1, max_length=50)
    duration: Optional[float] = Field(None, description="Audio duration in seconds")
    custom_context: Optional[str] = Field(None, description="Custom context or glossary for ASR and LLM")
    user_upn: Optional[str] = Field(None, description="UPN of the user creating the meeting")
    is_confidential: bool = Field(False, description="標記為機密會議（前端鎖複製/截圖警示/浮水印）")


# ============================================
# Summarize
# ============================================
class SummarizeRequestModel(BaseModel):
    transcript: str
    template_name: str = "general"


class SummarizeResponseModel(BaseModel):
    summary: str
    action_items: List[str]
    decisions: List[str]
    risks: List[str]


class RegenerateSummaryRequest(BaseModel):
    """Request body for regenerating summary"""
    template_name: str = Field("general", description="Summary template type")
    context: str = Field("", description="Additional context for summary")


# ============================================
# Speaker Mapping (Phase 8.1.3)
# ============================================
class SpeakerMappingEntry(BaseModel):
    display_name: str
    role: str
    color: str


class SpeakerMappingUpdate(BaseModel):
    mappings: Dict[str, SpeakerMappingEntry]  # { "Speaker_0": { display_name, role, color } }


# ============================================
# Intent classification
# ============================================
class IntentClassifyRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=100000,
        description="逐字稿純文字 (前 4000 字會送 Gemini)",
    )


# ============================================
# Feedback Report (Sprint 2d / PR22)
# ============================================
# 設計：階段 1 必填 3 項（issue_type / summary / severity）+ 階段 2 可選細節 +
# auto-attached metadata。enum 用 Literal 約束讓 Pydantic validate。

# 5 種 issue_type，使用者非專業用語以白話呈現（前端 label 處理）
IssueType = Literal[
    "transcript_inaccurate",  # 轉錄不準確
    "summary_wrong",          # 摘要內容不對
    "ui_clunky",              # 介面操作不順
    "system_error",           # 系統錯誤 / 卡住
    "other",                  # 其他
]

Severity = Literal["minor", "workaround", "blocker"]
Frequency = Literal["first", "rare", "common", "always"]
FeedbackStatus = Literal["open", "in_progress", "fixed", "wontfix", "duplicate"]


class FeedbackCreate(BaseModel):
    """POST /api/v1/feedback body — 階段 1 必填 + 階段 2 可選。"""
    # 階段 1 必填
    user_upn: str = Field(..., min_length=1, max_length=255)
    issue_type: IssueType
    summary: str = Field(..., min_length=5, max_length=200, description="一句話描述")
    severity: Severity

    # 階段 2 可選
    expected: Optional[str] = Field(None, max_length=2000, description="使用者期待的結果")
    actual: Optional[str] = Field(None, max_length=2000, description="使用者實際看到的結果")
    repro_steps: Optional[str] = Field(None, max_length=5000, description="重現步驟")
    frequency: Optional[Frequency] = None
    attachment_url: Optional[str] = Field(None, max_length=500)

    # Auto-attached metadata（前端送）
    meeting_id: Optional[str] = Field(None, max_length=36)
    page_url: Optional[str] = Field(None, max_length=500)
    browser_info: Optional[str] = Field(None, max_length=500)
    session_id: Optional[str] = Field(None, max_length=64)
    frontend_version: Optional[str] = Field(None, max_length=20)
    backend_version: Optional[str] = Field(None, max_length=20)
    # console_errors 用 List[Dict] 避免 Pydantic 嚴格驗證 — 各 browser 結構不一
    console_errors: Optional[List[Dict[str, Any]]] = None


class FeedbackRead(BaseModel):
    """GET response — admin / user 看 feedback 詳情。"""
    id: str
    user_upn: str
    issue_type: str
    summary: str
    severity: str

    expected: Optional[str] = None
    actual: Optional[str] = None
    repro_steps: Optional[str] = None
    frequency: Optional[str] = None
    attachment_url: Optional[str] = None

    meeting_id: Optional[str] = None
    page_url: Optional[str] = None
    browser_info: Optional[str] = None

    status: str
    assigned_to: Optional[str] = None
    resolved_at: Optional[datetime] = None
    admin_notes: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FeedbackPatch(BaseModel):
    """PATCH /api/v1/feedback/{id} — admin 改 status / assignee / notes。"""
    status: Optional[FeedbackStatus] = None
    assigned_to: Optional[str] = Field(None, max_length=255)
    admin_notes: Optional[str] = Field(None, max_length=5000)
    notify_user: Optional[bool] = None
