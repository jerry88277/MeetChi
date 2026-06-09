"""
Glossary Management Routes (C1: ASR Hotwords / Post-Correction)

Two-tier terminology correction:
  - Global (user_glossary): Per-user, shared across all meetings
  - Local (meeting_glossary): Per-meeting, overrides Global on conflict

Used by ASR pipeline:
  1. Whisper initial_prompt injection (hotwords)
  2. Post-transcription text replacement (wrong→correct)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserGlossary, MeetingGlossary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/glossary", tags=["Glossary"])


# ============================================
# Schemas
# ============================================

class GlossaryEntry(BaseModel):
    id: str
    wrong_text: str
    correct_text: str
    category: Optional[str] = None
    usage_count: Optional[int] = 0

class GlossaryCreate(BaseModel):
    wrong_text: str = Field(..., min_length=1, max_length=255)
    correct_text: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field("company", max_length=50)

class GlossaryUpdate(BaseModel):
    wrong_text: Optional[str] = Field(None, min_length=1, max_length=255)
    correct_text: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=50)

class MergedGlossaryResponse(BaseModel):
    """Merged Global + Local glossary for a meeting (Local overrides Global)"""
    entries: List[GlossaryEntry]
    global_count: int
    local_count: int
    hotword_prompt: str = Field(description="Whisper initial_prompt string")


# ============================================
# Global Glossary (user-level)
# ============================================

@router.get("/global", response_model=List[GlossaryEntry])
async def list_global_glossary(
    user_upn: str = Query(..., description="User's AD UPN"),
    db: Session = Depends(get_db),
):
    """List all global glossary entries for a user."""
    entries = db.query(UserGlossary).filter(
        UserGlossary.user_upn == user_upn.lower().strip()
    ).order_by(UserGlossary.usage_count.desc(), UserGlossary.created_at.desc()).all()
    
    return [GlossaryEntry(
        id=e.id, wrong_text=e.wrong_text, correct_text=e.correct_text,
        category=e.category, usage_count=e.usage_count
    ) for e in entries]


@router.post("/global", response_model=GlossaryEntry, status_code=201)
async def create_global_entry(
    body: GlossaryCreate,
    user_upn: str = Query(..., description="User's AD UPN"),
    db: Session = Depends(get_db),
):
    """Add a new global glossary entry."""
    upn = user_upn.lower().strip()
    existing = db.query(UserGlossary).filter(
        UserGlossary.user_upn == upn,
        UserGlossary.wrong_text == body.wrong_text.strip(),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Entry '{body.wrong_text}' already exists")
    
    entry = UserGlossary(
        user_upn=upn,
        wrong_text=body.wrong_text.strip(),
        correct_text=body.correct_text.strip(),
        category=body.category or "company",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    return GlossaryEntry(
        id=entry.id, wrong_text=entry.wrong_text, correct_text=entry.correct_text,
        category=entry.category, usage_count=entry.usage_count
    )


@router.put("/global/{entry_id}", response_model=GlossaryEntry)
async def update_global_entry(
    entry_id: str,
    body: GlossaryUpdate,
    user_upn: str = Query(..., description="User's AD UPN"),
    db: Session = Depends(get_db),
):
    """Update a global glossary entry."""
    entry = db.query(UserGlossary).filter(
        UserGlossary.id == entry_id,
        UserGlossary.user_upn == user_upn.lower().strip(),
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    if body.wrong_text is not None:
        entry.wrong_text = body.wrong_text.strip()
    if body.correct_text is not None:
        entry.correct_text = body.correct_text.strip()
    if body.category is not None:
        entry.category = body.category
    
    db.commit()
    return GlossaryEntry(
        id=entry.id, wrong_text=entry.wrong_text, correct_text=entry.correct_text,
        category=entry.category, usage_count=entry.usage_count
    )


@router.delete("/global/{entry_id}", status_code=204)
async def delete_global_entry(
    entry_id: str,
    user_upn: str = Query(..., description="User's AD UPN"),
    db: Session = Depends(get_db),
):
    """Delete a global glossary entry."""
    entry = db.query(UserGlossary).filter(
        UserGlossary.id == entry_id,
        UserGlossary.user_upn == user_upn.lower().strip(),
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    db.delete(entry)
    db.commit()


# ============================================
# Local Glossary (meeting-level)
# ============================================

@router.get("/meeting/{meeting_id}", response_model=List[GlossaryEntry])
async def list_meeting_glossary(
    meeting_id: str,
    db: Session = Depends(get_db),
):
    """List all local glossary entries for a specific meeting."""
    entries = db.query(MeetingGlossary).filter(
        MeetingGlossary.meeting_id == meeting_id
    ).order_by(MeetingGlossary.created_at.desc()).all()
    
    return [GlossaryEntry(
        id=e.id, wrong_text=e.wrong_text, correct_text=e.correct_text,
        category=None, usage_count=0
    ) for e in entries]


@router.post("/meeting/{meeting_id}", response_model=GlossaryEntry, status_code=201)
async def create_meeting_entry(
    meeting_id: str,
    body: GlossaryCreate,
    db: Session = Depends(get_db),
):
    """Add a new local glossary entry for a meeting."""
    existing = db.query(MeetingGlossary).filter(
        MeetingGlossary.meeting_id == meeting_id,
        MeetingGlossary.wrong_text == body.wrong_text.strip(),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Entry '{body.wrong_text}' already exists for this meeting")
    
    entry = MeetingGlossary(
        meeting_id=meeting_id,
        wrong_text=body.wrong_text.strip(),
        correct_text=body.correct_text.strip(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    return GlossaryEntry(
        id=entry.id, wrong_text=entry.wrong_text, correct_text=entry.correct_text,
        category=None, usage_count=0
    )


@router.delete("/meeting/{meeting_id}/{entry_id}", status_code=204)
async def delete_meeting_entry(
    meeting_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
):
    """Delete a local glossary entry."""
    entry = db.query(MeetingGlossary).filter(
        MeetingGlossary.id == entry_id,
        MeetingGlossary.meeting_id == meeting_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    db.delete(entry)
    db.commit()


# ============================================
# Merged Glossary (for ASR pipeline)
# ============================================

@router.get("/merged/{meeting_id}", response_model=MergedGlossaryResponse)
async def get_merged_glossary(
    meeting_id: str,
    user_upn: str = Query(..., description="User's AD UPN"),
    db: Session = Depends(get_db),
):
    """
    Get merged Global + Local glossary for a meeting.
    Union strategy: Local overrides Global on key (wrong_text) conflict.
    Also returns the Whisper initial_prompt hotword string.
    """
    upn = user_upn.lower().strip()
    
    # Get Global entries
    global_entries = db.query(UserGlossary).filter(
        UserGlossary.user_upn == upn
    ).all()
    
    # Get Local entries
    local_entries = db.query(MeetingGlossary).filter(
        MeetingGlossary.meeting_id == meeting_id
    ).all()
    
    # Merge: Local overrides Global on wrong_text conflict
    merged = {}
    for g in global_entries:
        merged[g.wrong_text] = GlossaryEntry(
            id=g.id, wrong_text=g.wrong_text, correct_text=g.correct_text,
            category=g.category, usage_count=g.usage_count
        )
    for l in local_entries:
        merged[l.wrong_text] = GlossaryEntry(
            id=l.id, wrong_text=l.wrong_text, correct_text=l.correct_text,
            category=None, usage_count=0
        )
    
    # Build Whisper initial_prompt hotword string
    correct_terms = list({e.correct_text for e in merged.values()})
    hotword_prompt = ""
    if correct_terms:
        hotword_prompt = "以下是本次會議可能出現的專有名詞：" + "、".join(correct_terms)
    
    return MergedGlossaryResponse(
        entries=list(merged.values()),
        global_count=len(global_entries),
        local_count=len(local_entries),
        hotword_prompt=hotword_prompt,
    )


@router.post("/apply/{meeting_id}")
async def apply_correction(
    meeting_id: str,
    user_upn: str = Query(..., description="User's AD UPN"),
    db: Session = Depends(get_db),
):
    """
    Retroactively apply glossary corrections to an existing meeting's segments.
    Use after adding new glossary entries for already-transcribed meetings.
    """
    from app.tasks import apply_glossary_correction
    
    corrected = apply_glossary_correction(db, meeting_id, user_upn)
    return {"meeting_id": meeting_id, "segments_corrected": corrected}
