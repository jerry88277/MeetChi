"""
Pydantic API schemas — request/response models for FastAPI routes.

Extracted from main.py to keep route files schema-aware without
re-importing from a 1.8k-line module.
"""

from datetime import datetime
from typing import List, Optional, Dict
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
    language: str
    template_name: str
    transcript_raw: Optional[str]
    transcript_polished: Optional[str]
    summary_json: Optional[str]
    speaker_mappings: Optional[str] = None  # Phase 8.1.3

    transcript_segments: List[TranscriptSegmentRead] = []  # Include segments for detail view

    class Config:
        from_attributes = True


class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    language: str = Field("zh", min_length=2, max_length=10)
    template_name: str = Field("general", min_length=1, max_length=50)
    duration: Optional[float] = Field(None, description="Audio duration in seconds")
    custom_context: Optional[str] = Field(None, description="Custom context or glossary for ASR and LLM")
    user_upn: Optional[str] = Field(None, description="UPN of the user creating the meeting")


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
