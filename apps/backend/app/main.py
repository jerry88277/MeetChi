from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.responses import JSONResponse # Import JSONResponse
from fastapi.middleware.cors import CORSMiddleware # Import CORSMiddleware
from sqlalchemy import create_engine, String, DateTime, Text, Enum, Float, Boolean, Integer, desc # Import missing types
from sqlalchemy.orm import sessionmaker, Session, relationship # Import relationship for eager loading
from sqlalchemy.ext.declarative import declarative_base # Need to re-declare Base
from sqlalchemy import Column, ForeignKey # Need Column and ForeignKey
from sqlalchemy.orm import selectinload # New: For eager loading relationships

import os
import io
import asyncio
import numpy as np
import logging
import httpx  # For GPU ASR service-to-service HTTP calls
import google.auth.transport.requests as google_auth_requests
import google.oauth2.id_token as google_id_token
import uuid # For UUID generation
from datetime import datetime # For datetime fields
from dotenv import load_dotenv
import time
import json
import sys
from logging.handlers import TimedRotatingFileHandler
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import wave 
import difflib # Import difflib for fuzzy matching
import re
import tempfile
from google.cloud import storage as gcs_storage

from app.aligner import ScriptAligner, MultiSpeakerScriptAligner



# --- Logging Configuration ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()
# Cloud Run captures stderr — use stderr + flush for structured logging visibility
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
log_filename = os.path.join(LOG_DIR, "backend.log")
file_handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, backupCount=7, encoding="utf-8")
file_handler.suffix = "%Y-%m-%d"
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
app_logger = logging.getLogger(__name__)

# --- App Initialization ---
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# --- Re-declare Base if needed, or import from models.py ---
# Assuming Base is already declared in models.py and imported via 'from app.models import Base, ...'
from app.models import Base, Meeting, MeetingStatus, TranscriptSegment, Artifact, TaskStatus, User, MeetingParticipant # Import all relevant models
from app.vad import VADAudioBuffer

from app.llm_utils import get_gemini_client, polish_text, generate_summary, GEMINI_MODEL

# Gemini Setup handled in llm_utils



async def get_transcription_gemini(audio_np, lang="zh", prompt=""):
    """
    Transcribe audio using Gemini API (multimodal input).
    
    Args:
        audio_np: numpy float32 array of audio samples at 16kHz
        lang: source language code ('zh', 'en', etc.)
        prompt: context/initial prompt for better accuracy
    Returns:
        Transcribed text string
    """
    client = get_gemini_client()
    if client is None:
        raise RuntimeError("Gemini client not initialized. Set GCP_PROJECT or GEMINI_API_KEY.")
    
    import soundfile as sf
    
    # Convert numpy array to WAV bytes in memory
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, audio_np, 16000, format='WAV')
    wav_bytes = wav_buffer.getvalue()
    
    lang_map = {"zh": "繁體中文", "en": "English", "ja": "日本語"}
    lang_name = lang_map.get(lang, lang)
    
    system_prompt = (
        f"你是語音轉文字引擎。請將音頻精確轉寫為{lang_name}文字。"
        "只輸出轉寫文字，不要添加任何額外說明、標點符號修飾或格式化。"
        "如果音頻中沒有語音或只有噪音，回傳空字串。"
    )
    
    user_content = []
    if prompt:
        user_content.append(f"上下文提示：{prompt}")
    user_content.append("請轉寫以下音頻：")
    
    from google.genai import types
    user_content.append(types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"))
    
    def _call_gemini_asr():
        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
            )
        )
    
    # Run synchronous Gemini call in thread pool
    response = await asyncio.to_thread(_call_gemini_asr)
    
    result = response.text.strip() if response.text else ""
    return result


# Conditional import for GPU-dependent ASR functions (optional local mode)
try:
    from scripts.transcribe_sprint0 import get_transcription, load_asr_model, correct_keywords, logger as asr_logger
    LOCAL_ASR_AVAILABLE = True
except ImportError as e:
    asr_logger = logging.getLogger("asr_fallback")
    asr_logger.info(f"Local ASR not available: {e}. Using Gemini API for ASR.")
    LOCAL_ASR_AVAILABLE = False
    
    def get_transcription(*args, **kwargs):
        raise NotImplementedError("Local ASR not available. Use Gemini API.")
    
    def load_asr_model(*args, **kwargs):
        pass
    
    def correct_keywords(text):
        return text


from app.database import engine, SessionLocal, get_db, DATABASE_URL
from app.models import Base
from sqlalchemy import text
import os

# Auto-create tables (SQLite and initial PostgreSQL setup)
if DATABASE_URL.startswith("postgresql"):
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
elif DATABASE_URL.startswith("sqlite"):
    db_file_path = DATABASE_URL.replace("sqlite:///", "")
    if db_file_path.startswith("/"):
        os.makedirs(os.path.dirname(db_file_path), exist_ok=True)

Base.metadata.create_all(bind=engine)

# Phase 8.1: Safe column migration for existing tables
# create_all() doesn't add columns to existing tables in PostgreSQL
if DATABASE_URL.startswith("postgresql"):
    with engine.connect() as conn:
        # Add missing columns if not exist
        for col_name in ["speaker_mappings", "custom_prompt"]:
            conn.execute(text(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='meetings' AND column_name='{col_name}'
                    ) THEN
                        ALTER TABLE meetings ADD COLUMN {col_name} TEXT;
                    END IF;
                END $$;
            """))
        conn.commit()

# Phase RAG-AC: Safe-create access control tables (users, meeting_participants)
# Alembic migration f7a9d3e1c5b2 handles this formally; this block is a safety net
# in case the Cloud Run container starts before migration runs.
if DATABASE_URL.startswith("postgresql"):
    with engine.connect() as conn:
        # Ensure pgvector is available
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

        # Ensure Enum types exist
        conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'participantrole') THEN
                    CREATE TYPE participantrole AS ENUM ('owner', 'participant', 'viewer');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'accesssource') THEN
                    CREATE TYPE accesssource AS ENUM ('upload', 'participant', 'granted');
                END IF;
            END $$;
        """))
        conn.commit()
        
    # ALTER TYPE requires AUTOCOMMIT isolation level
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as autocommit_conn:
        try:
            autocommit_conn.execute(text("ALTER TYPE participantrole ADD VALUE IF NOT EXISTS 'owner';"))
        except Exception:
            pass
        try:
            autocommit_conn.execute(text("ALTER TYPE accesssource ADD VALUE IF NOT EXISTS 'upload';"))
        except Exception:
            pass

    with engine.connect() as conn:
        # users table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id            VARCHAR(36)  PRIMARY KEY,
                ad_upn        VARCHAR(255) NOT NULL UNIQUE,
                display_name  VARCHAR(255),
                department    VARCHAR(255),
                is_admin      BOOLEAN      NOT NULL DEFAULT FALSE,
                created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
                last_login_at TIMESTAMP
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_users_ad_upn ON users (ad_upn);"
        ))

        # owner_upn column in meetings
        conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'meetings' AND column_name = 'owner_upn'
                ) THEN
                    ALTER TABLE meetings ADD COLUMN owner_upn VARCHAR(255);
                END IF;
            END $$;
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_meetings_owner_upn ON meetings (owner_upn);"
        ))

        # meeting_participants table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meeting_participants (
                id             VARCHAR(36)  PRIMARY KEY,
                meeting_id     VARCHAR(36)  NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                user_upn       VARCHAR(255) NOT NULL REFERENCES users(ad_upn) ON DELETE CASCADE,
                role           participantrole NOT NULL DEFAULT 'participant',
                access_source  accesssource    NOT NULL DEFAULT 'participant',
                granted_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
                granted_by_upn VARCHAR(255) REFERENCES users(ad_upn),
                CONSTRAINT uq_meeting_participant UNIQUE (meeting_id, user_upn)
            );
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_mp_user_upn    ON meeting_participants (user_upn);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_mp_meeting_id  ON meeting_participants (meeting_id);"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_mp_upn_meeting ON meeting_participants (user_upn, meeting_id);"
        ))
        conn.commit()
        
        # BACKFILL: Find meetings with no participants and assign them to 'test@company.com'
        conn.execute(text("""
            INSERT INTO users (id, ad_upn, display_name, is_admin)
            VALUES (:id, 'test@company.com', 'Test User', true)
            ON CONFLICT (ad_upn) DO NOTHING;
        """), {"id": str(uuid.uuid4())})
        
        conn.execute(text("""
            UPDATE meetings SET owner_upn = 'test@company.com'
            WHERE owner_upn IS NULL;
        """))
        
        conn.execute(text("""
            INSERT INTO meeting_participants (id, meeting_id, user_upn, role, access_source, granted_at)
            SELECT gen_random_uuid()::varchar(36), m.id, 'test@company.com', 'owner', 'upload', NOW()
            FROM meetings m
            WHERE NOT EXISTS (
                SELECT 1 FROM meeting_participants mp WHERE mp.meeting_id = m.id
            );
        """))
        conn.commit()
        
    app_logger.info("[Startup] RAG access control tables verified/created and orphan meetings backfilled.")


from app.tasks import generate_meeting_minutes  # Now a direct function (not Celery task)
from app.routes import api_router  # Import routes


app = FastAPI(
    title="MeetChi API",
    description="Meeting Intelligence Platform API",
    version="1.0.0"
)
# Dynamic CORS setup for E2E testing
is_e2e_mode = os.getenv("NEXT_PUBLIC_E2E_TEST_MODE", "false").lower() == "true"
cors_origins = ["*"] if is_e2e_mode else [
    "http://localhost:3000",
    "https://meetchi-staging-test-wfqjx2j42q-de.a.run.app",
    "https://your-production-domain.com", # TODO: Update this when deploying to actual prod domain
    "https://meetchi-frontend-705495828555.asia-southeast1.run.app",
    "https://meetchi-frontend-wfqjx2j42q-as.a.run.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if not is_e2e_mode else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

# Health check endpoint for Cloud Run probes
# CRITICAL: Must verify DB connectivity — a static "healthy" response
# masked the 2026-03-12 env var wipe incident for hours.
@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run probes.
    
    Validates DB connectivity via SELECT 1. Returns 503 if DB unreachable,
    which causes Cloud Run startup/liveness probes to fail and prevents
    traffic routing to a broken revision.
    """
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "healthy", "service": "meetchi-backend"}
    except Exception as e:
        app_logger.error(f"Health check FAILED — DB unreachable: {e}")
        return JSONResponse(
            content={"status": "unhealthy", "service": "meetchi-backend", "reason": "db_unreachable"},
            status_code=503
        )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models for API ---
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
    
    transcript_segments: List[TranscriptSegmentRead] = [] # Include segments for detail view

    class Config:
        from_attributes = True

class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    language: str = Field("zh", min_length=2, max_length=10)
    template_name: str = Field("general", min_length=1, max_length=50)
    duration: Optional[float] = Field(None, description="Audio duration in seconds")
    custom_context: Optional[str] = Field(None, description="Custom context or glossary for ASR and LLM")
    user_upn: Optional[str] = Field(None, description="UPN of the user creating the meeting")

class SummarizeRequestModel(BaseModel):
    transcript: str
    template_name: str = "general"

class SummarizeResponseModel(BaseModel):
    summary: str
    action_items: List[str]
    decisions: List[str]
    risks: List[str]


# --- API Endpoints ---

@app.post("/api/v1/meetings", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def create_meeting(meeting_data: MeetingCreate, db: Session = Depends(get_db)):
    """
    Creates a new meeting entry.
    """
    upn = meeting_data.user_upn or 'test@company.com'
    
    # 1. Ensure user exists
    user_obj = db.query(User).filter(User.ad_upn == upn).first()
    if not user_obj:
        user_obj = User(
            id=str(uuid.uuid4()),
            ad_upn=upn,
            display_name=upn.split('@')[0],
            is_admin=True if upn == 'test@company.com' else False
        )
        db.add(user_obj)
        db.flush()
        
    # 2. Create Meeting
    db_meeting = Meeting(
        title=meeting_data.title,
        language=meeting_data.language,
        template_name=meeting_data.template_name,
        duration=meeting_data.duration,
        custom_prompt=meeting_data.custom_context,
        owner_upn=upn
    )
    db.add(db_meeting)
    db.flush()
    
    # 3. Create Participant binding
    db_participant = MeetingParticipant(
        id=str(uuid.uuid4()),
        meeting_id=db_meeting.id,
        user_upn=upn,
        role='owner',
        access_source='upload'
    )
    db.add(db_participant)
    
    db.commit()
    db.refresh(db_meeting) # Refresh to get ID and other defaults
    return MeetingRead.from_orm(db_meeting) # Return Pydantic model

@app.get("/api/v1/meetings", response_model=List[MeetingRead])
async def list_meetings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    List historical meetings.
    """
    meetings = db.query(Meeting).options(
        # Load segments if needed, or keep it light for list view
        # selectinload(Meeting.transcript_segments)
    ).order_by(desc(Meeting.created_at)).offset(skip).limit(limit).all()
    return [MeetingRead.from_orm(m) for m in meetings]

@app.get("/api/v1/meetings/{meeting_id}", response_model=MeetingRead)
async def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """
    Get meeting details including transcript and summary.
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).options(
        selectinload(Meeting.transcript_segments), # Eager load segments
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingRead.from_orm(meeting)

@app.post("/api/v1/meetings/{meeting_id}/add_segments")
async def add_transcript_segments(meeting_id: str, segments: List[TranscriptSegmentCreate], db: Session = Depends(get_db)):
    """
    Adds a list of transcript segments to a specific meeting.
    This is typically called after a recording has finished.
    """
    db_meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not db_meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    new_segments = []
    for segment_data in segments:
        data = segment_data.dict(exclude_unset=True)
        if "id" not in data or data["id"] is None:
            data["id"] = str(uuid.uuid4())
        new_segment = TranscriptSegment(**data, meeting_id=meeting_id) # Assign meeting_id
        db.add(new_segment)
        new_segments.append(new_segment)
    
    db.commit()
    db.refresh(db_meeting) 
    return {"message": f"Added {len(new_segments)} segments to meeting {meeting_id}"}


@app.post("/api/v1/meetings/{meeting_id}/generate-summary")
def trigger_summary_generation(
    meeting_id: str, 
    template_type: str = "general", 
    context: str = "",
    length: str = "medium",
    style: str = "formal",
    background_tasks: BackgroundTasks = None, 
    db: Session = Depends(get_db)
):
    """
    Trigger background task to generate meeting minutes.
    FORCE FALLBACK MODE: Skip Celery to avoid Redis connection timeouts in dev environment without Redis.
    """
    app_logger.info(f"Triggering local background summary for {meeting_id}")
    
    # Fallback: Run in background task (local thread)
    from app.tasks import generate_summary_core
    background_tasks.add_task(generate_summary_core, meeting_id, template_type, context, length, style)
    
    return JSONResponse(
        content={"message": "Summary generation started (Local Force)", "task_id": "local-force"},
        status_code=status.HTTP_200_OK
    )


class RegenerateSummaryRequest(BaseModel):
    """Request body for regenerating summary"""
    template_name: str = Field("general", description="Summary template type")
    context: str = Field("", description="Additional context for summary")


@app.post("/api/v1/meetings/{meeting_id}/regenerate-summary")
async def regenerate_summary(
    meeting_id: str,
    request: RegenerateSummaryRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Regenerate summary for an existing meeting.
    Phase D: Saves existing summary as a version before re-generation.
    """
    # Check if meeting exists
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    # Check if meeting has transcript content
    if not meeting.transcript_raw and not meeting.transcript_polished:
        # Check if there are transcript segments
        segment_count = db.query(TranscriptSegment).filter(
            TranscriptSegment.meeting_id == meeting_id
        ).count()
        if segment_count == 0:
            raise HTTPException(
                status_code=400, 
                detail="Meeting has no transcript content to summarize"
            )
    
    # Phase D: Save existing summary as a version before overwriting
    if meeting.summary_json:
        from app.models import SummaryVersion
        import uuid as _uuid
        version = SummaryVersion(
            id=str(_uuid.uuid4()),
            meeting_id=meeting_id,
            template_name=meeting.template_name or "general",
            summary_json=meeting.summary_json,
        )
        db.add(version)
        app_logger.info(f"Saved summary version for meeting {meeting_id} (template: {meeting.template_name})")
    
    # Clear existing summary and reset status to processing
    meeting.summary_json = None
    meeting.status = MeetingStatus.PROCESSING
    meeting.updated_at = datetime.utcnow()
    db.commit()
    
    app_logger.info(f"Regenerating summary for meeting {meeting_id} with template {request.template_name}")
    
    # Trigger summary generation in background
    from app.tasks import generate_summary_core
    background_tasks.add_task(
        generate_summary_core, 
        meeting_id, 
        request.template_name, 
        request.context,
        "medium",
        "formal"
    )
    
    return JSONResponse(
        content={
            "message": "Summary regeneration started",
            "meeting_id": meeting_id,
            "status": "processing"
        },
        status_code=status.HTTP_200_OK
    )

@app.get("/api/v1/meetings/{meeting_id}/summary-versions")
async def list_summary_versions(meeting_id: str, db: Session = Depends(get_db)):
    """Phase D: List all saved summary versions for a meeting."""
    from app.models import SummaryVersion
    versions = db.query(SummaryVersion).filter(
        SummaryVersion.meeting_id == meeting_id
    ).order_by(SummaryVersion.created_at.desc()).all()
    
    return [
        {
            "id": v.id,
            "template_name": v.template_name,
            "summary_json": v.summary_json,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]

@app.post("/api/v1/meetings/{meeting_id}/restore-summary-version/{version_id}")
async def restore_summary_version(meeting_id: str, version_id: str, db: Session = Depends(get_db)):
    """Phase D: Restore a specific summary version as the current summary."""
    from app.models import SummaryVersion
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    version = db.query(SummaryVersion).filter(
        SummaryVersion.id == version_id,
        SummaryVersion.meeting_id == meeting_id,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Save current as a version first
    if meeting.summary_json:
        import uuid as _uuid
        current_version = SummaryVersion(
            id=str(_uuid.uuid4()),
            meeting_id=meeting_id,
            template_name=meeting.template_name or "general",
            summary_json=meeting.summary_json,
        )
        db.add(current_version)
    
    # Restore the selected version
    meeting.summary_json = version.summary_json
    meeting.template_name = version.template_name
    meeting.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Summary restored", "template_name": version.template_name}

CORRECTIONS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "corrections.json")

@app.get("/api/v1/settings/corrections")
async def get_corrections():
    """Get current keyword correction rules."""
    if os.path.exists(CORRECTIONS_CONFIG_PATH):
        with open(CORRECTIONS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@app.post("/api/v1/settings/corrections")
async def update_corrections(corrections: dict):
    """Update keyword correction rules."""
    try:
        with open(CORRECTIONS_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(corrections, f, ensure_ascii=False, indent=4)
        return {"message": "Corrections updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save corrections: {e}")

@app.delete("/api/v1/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """
    Delete a meeting and its associated resources (audio file, transcripts).
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # 1. Delete Audio File
    if meeting.audio_url and os.path.exists(meeting.audio_url):
        try:
            os.remove(meeting.audio_url)
            app_logger.info(f"Deleted audio file: {meeting.audio_url}")
        except Exception as e:
            app_logger.error(f"Failed to delete audio file {meeting.audio_url}: {e}")

    # 2. Delete Transcripts (Cascade delete handles this usually, but let's be explicit if needed)
    # SQLAlchemy relationship with cascade="all, delete" is preferred, but manual for now:
    db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).delete()
    
    # 3. Delete Meeting Record
    db.delete(meeting)
    db.commit()
    
    return None


# --- Phase 8.1.3: Speaker Mappings API ---
class SpeakerMappingEntry(BaseModel):
    display_name: str
    role: str
    color: str

class SpeakerMappingUpdate(BaseModel):
    mappings: Dict[str, SpeakerMappingEntry]  # { "Speaker_0": { display_name, role, color } }

@app.patch("/api/v1/meetings/{meeting_id}/speakers")
async def update_speaker_mappings(
    meeting_id: str,
    update: SpeakerMappingUpdate,
    db: Session = Depends(get_db)
):
    """Update speaker label mappings for a meeting (Phase 8.1.3)."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    meeting.speaker_mappings = json.dumps(
        {k: v.dict() for k, v in update.mappings.items()},
        ensure_ascii=False
    )
    meeting.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Speaker mappings updated", "meeting_id": meeting_id}

@app.post("/api/v1/summarize", response_model=SummarizeResponseModel)
async def summarize_full_transcript(request_data: SummarizeRequestModel):
    """
    Triggers a summarization task for a full transcript using the LLM service.
    """
    app_logger.info(f"Received summarization request for transcript (len: {len(request_data.transcript)}) with template: {request_data.template_name}")
    try:
        client = get_gemini_client()
        if not client:
            raise HTTPException(status_code=500, detail="Gemini client unavailable")
            
        def _run_summary():
            return generate_summary(
                client=client,
                text=request_data.transcript,
                template_name=request_data.template_name
            )
            
        summary_data = await asyncio.to_thread(_run_summary)
        
        if "error" in summary_data:
            raise Exception(summary_data["error"])
            
        return SummarizeResponseModel(
            summary=summary_data.get("summary", "無法生成摘要。"),
            action_items=summary_data.get("action_items", []),
            decisions=summary_data.get("decisions", []),
            risks=summary_data.get("risks", [])
        )
    except Exception as e:
        app_logger.error(f"Error calling Gemini for summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {e}")


# Load ASR model during startup (optional - may fail on Cloud Run CPU environment)
@app.on_event("startup")
async def on_startup():
    app_logger.info("Application startup event triggered.")
    Base.metadata.create_all(bind=engine)
    app_logger.info("Database tables checked/created.")
    
    # ASR model pre-loading is optional - in Cloud Run CPU environment,
    # this will fail because faster-whisper requires GPU libraries.
    # ASR transcription should be handled by a separate GPU-enabled service.
    enable_asr_preload = os.getenv("ENABLE_ASR_PRELOAD", "false").lower() == "true"
    if enable_asr_preload:
        app_logger.info("Pre-loading ASR model (ENABLE_ASR_PRELOAD=true)...")
        try:
            await asyncio.to_thread(load_asr_model)
            app_logger.info("ASR model pre-loaded successfully.")
        except Exception as e:
            app_logger.warning(f"ASR model pre-loading failed (non-fatal): {e}")
            app_logger.warning("ASR transcription will not be available locally. Use LLM service instead.")
    else:
        app_logger.info("Skipping ASR model pre-loading (ENABLE_ASR_PRELOAD not set).")


@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        db.scalar(text("SELECT 1"))
        return {"message": "Database connection successful!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

async def polish_transcription_task(segment_id: str, transcript_text: str, previous_context: str, source_lang: str, target_lang: str, websocket: WebSocket):
    # Async task to call Gemini directly for polishing and send result back to WebSocket.
    try:
        client = get_gemini_client()
        if not client:
            raise Exception("Gemini client unavailable")

        # Run synchronous polish_text in thread pool
        def _run_polish():
            return polish_text(
                client=client,
                raw_text=transcript_text,
                source_lang=source_lang,
                target_lang=target_lang
            )

        polished_data = await asyncio.to_thread(_run_polish)
        
        if "error" in polished_data:
            raise Exception(polished_data["error"])
        
        refined_text = polished_data.get("polished_text", transcript_text)
        translated_text = polished_data.get("translated", "")
        
        app_logger.info(f"Polished [{segment_id}]: {refined_text} | Translated: {translated_text}")

        # Send polished transcript to frontend
        try:
            await websocket.send_json({
                "type": "polished",
                "id": segment_id,
                "content": refined_text, 
                "translated": translated_text
            })
        except RuntimeError as e:
            # WebSocket might be closed/disconnected
            app_logger.warning(f"Could not send polished text, websocket probably closed: {e}")
        except Exception as e:
            app_logger.error(f"Error sending polished text via websocket: {e}")

    except Exception as e:
        app_logger.error(f"Polishing task failed for segment {segment_id}: {e}")
        # Optionally notify frontend of error
        try:
            await websocket.send_json({
                "type": "error",
                "id": segment_id,
                "content": "Polishing failed."
            })
        except:
            pass

# WebSocket Endpoint for Real-time Transcription
@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket, db: Session = Depends(get_db)): # Inject DB session
    await websocket.accept()
    app_logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} connected for transcription.")

    # Audio is managed by frontend IndexedDB and uploaded via REST API.
    # The WebSocket is strictly stateless for live transcription.
    

    # Store meeting_id received from frontend for associating audio
    current_meeting_id: Optional[str] = None

    # Initialize VAD Buffer (Defaults from vad.py: 5.0s max)
    RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2 # 16-bit audio
    vad_buffer = VADAudioBuffer(
        sample_rate=RATE, 
        silence_threshold=0.3, 
        min_silence_duration=0.6, 
        max_duration=7
    )
    
    # Pseudo-streaming state
    last_partial_time = time.time()
    current_segment_id = str(uuid.uuid4())
    previous_context = "" # Store the last finalized transcript for context
    
    # --- Overlapping Window Buffer ---
    # Store history of processed audio to prepend to next segment
    # Set to 0.0 to prevent duplication issues, relying on VAD to split at silence.
    OVERLAP_DURATION_SECONDS = 0.0 
    last_flushed_segment_np = np.array([], dtype=np.float32) # Store the last VAD-flushed segment
    
    # Language Configuration (Default: ZH -> EN)
    source_lang = "zh"
    target_lang = "en"
    
    # Custom Initial Prompt from Frontend
    custom_initial_prompt = ""
    
    operation_mode = "transcription" # Default mode
    script_aligner = MultiSpeakerScriptAligner() # Initialize Multi-Speaker Aligner

    first_audio_time = None
    current_meeting_id = None

    # --- WebSocket Heartbeat (prevents Cloud Run proxy idle timeout ~60s) ---
    WS_PING_INTERVAL = 25  # Send ping every 25s of no activity

    # Background heartbeat task — keeps connection alive without corrupting receive()
    async def _heartbeat_ping(ws: WebSocket, interval: int = 25):
        # Send periodic pings to prevent Cloud Run proxy idle timeout.
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break  # WebSocket closed
        except asyncio.CancelledError:
            pass  # Task cancelled on disconnect — expected

    heartbeat_task = asyncio.create_task(_heartbeat_ping(websocket, WS_PING_INTERVAL))

    try:
        while True:
            # Receive message — direct call, no wait_for wrapping
            message = await websocket.receive()
            
            # Check for WebSocket disconnect message
            if message.get("type") == "websocket.disconnect":
                app_logger.info("Received WebSocket disconnect frame.")
                break
            # 1. Handle Configuration Messages (Text)
            if "text" in message:
                try:
                    config = json.loads(message["text"])
                    # Handle ping/pong heartbeat
                    if config.get("type") == "pong":
                        continue  # Heartbeat response, skip processing
                    if config.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue
                    if config.get("type") == "config":
                        source_lang = config.get("source_lang", source_lang)
                        target_lang = config.get("target_lang", target_lang)
                        custom_initial_prompt = config.get("initial_prompt", "")
                        # Receive meeting_id from frontend (essential for saving audio_url)
                        if "meeting_id" in config:
                            current_meeting_id = config["meeting_id"]
                            app_logger.info(f"Received meeting_id: {current_meeting_id}")
                        
                        if "overlap_duration" in config:
                            OVERLAP_DURATION_SECONDS = float(config["overlap_duration"])
                        
                        if "mode" in config:
                            operation_mode = config["mode"]
                            app_logger.info(f"[DEBUG] Received mode: {operation_mode}")
                            # If alignment mode, load the script from initial_prompt
                            if operation_mode == "alignment":
                                app_logger.info(f"[DEBUG] Alignment mode activated. initial_prompt length: {len(custom_initial_prompt)}")
                                app_logger.info(f"[DEBUG] initial_prompt preview: {custom_initial_prompt[:200]}")
                                script_aligner.load_script(custom_initial_prompt)
                                app_logger.info(f"[DEBUG] Loaded {len(script_aligner.segments)} segments for Alignment Mode.")
                                app_logger.info(f"[DEBUG] Flattened text length: {len(script_aligner.full_cn_text)} characters")
                                if len(script_aligner.segments) > 0:
                                    first_seg = script_aligner.segments[0]
                                    app_logger.info(f"[DEBUG] First segment: [{first_seg['start_idx']}-{first_seg['end_idx']}] {first_seg['source'][:30]}...")

                        app_logger.info(f"Config updated: {source_lang} -> {target_lang} | Prompt len: {len(custom_initial_prompt)} | Overlap: {OVERLAP_DURATION_SECONDS} | Mode: {operation_mode}")
                except Exception as e:
                    app_logger.error(f"Failed to parse config message: {e}")
                continue # Skip audio processing for this loop iteration

            # 2. Handle Audio Data (Bytes)
            if "bytes" in message:
                data = message["bytes"]
                if first_audio_time is None:
                    first_audio_time = time.time()
                    app_logger.info("First audio packet received. Starting forced speech window.")
                
            else:
                continue # Should not happen if receive() returns correctly
            
            # Process chunk with VAD
            # Force speech for the first 3.0 seconds to prevent initial clipping
            is_initial_phase = False
            if first_audio_time is not None:
                is_initial_phase = (time.time() - first_audio_time) < 3.0
            
            # Returns bytes only if a split point (silence or max duration) is reached
            audio_bytes = vad_buffer.process_chunk(data, force_speech=is_initial_phase)

            # --- Partial Transcription ---
            # REMOVED: Backend no longer does partial ASR.
            # Partial transcription is handled by the frontend using Web Speech API (free, <500ms latency).
            # Backend only handles Final transcription via Gemini API when VAD detects a split.


            # --- Final Transcription (Split Event) ---
            if audio_bytes:
                audio_np_current = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                audio_for_transcription = audio_np_current
                # Prepend overlap from the last flushed segment
                if last_flushed_segment_np.size > 0:
                    overlap_samples = int(OVERLAP_DURATION_SECONDS * RATE)
                    overlap_from_previous = last_flushed_segment_np[-min(overlap_samples, last_flushed_segment_np.size):]
                    audio_for_transcription = np.concatenate((overlap_from_previous, audio_np_current))
                
                # Update last flushed segment for next overlap
                last_flushed_segment_np = audio_np_current
                
                if audio_for_transcription.size > 0:
                    app_logger.info(f"Transcribing {len(audio_for_transcription)/RATE:.2f} seconds of audio (VAD split with overlap)...")
                    
                    # Use previous_context as initial_prompt for ASR consistency
                    combined_prompt = f"{custom_initial_prompt} {previous_context}".strip()
                    
                    try:
                        # Gemini API ASR — async call with timeout
                        transcript_text = await asyncio.wait_for(
                            get_transcription_gemini(audio_for_transcription, source_lang, combined_prompt),
                            timeout=30.0
                        )
                        app_logger.info(f"Gemini ASR Output: '{transcript_text}'")
                    except asyncio.TimeoutError:
                        app_logger.error(f"Gemini ASR timed out for segment {current_segment_id}. Skipping segment.")
                        transcript_text = ""
                    except Exception as e:
                        app_logger.error(f"Gemini ASR error for segment {current_segment_id}: {e}", exc_info=True)
                        transcript_text = ""
                    
                    if transcript_text:
                        app_logger.info(f"Raw Transcription [{current_segment_id}]: {transcript_text}")

                        # 1. Send raw transcript (Finalize the segment)
                        await websocket.send_json({
                            "type": "raw",
                            "id": current_segment_id,
                            "content": transcript_text
                        })

                        # --- Alignment Mode Logic ---
                        alignment_success = False
                        if operation_mode == "alignment" and script_aligner.has_script():
                            # Apply corrections before matching
                            corrected_text = correct_keywords(transcript_text)
                            if corrected_text != transcript_text:
                                app_logger.info(f"[DEBUG] Corrections applied: '{transcript_text}' -> '{corrected_text}'")
                            
                            app_logger.info(f"[DEBUG] Attempting alignment for transcript: '{corrected_text}'")
                            app_logger.info(f"[DEBUG] Current cursor position: {script_aligner.current_cursor} / {len(script_aligner.full_cn_text)}")
                            
                            match_result = script_aligner.find_match(corrected_text, threshold=0.4, alignment_mode=True)
                            if match_result:
                                # Log match details
                                is_global = match_result.get('is_global_resync', False)
                                is_low_conf = match_result.get('low_confidence', False)
                                resync_tag = " [GLOBAL RESYNC]" if is_global else ""
                                conf_tag = " [LOW CONFIDENCE]" if is_low_conf else ""
                                match_symbol = "⚠️" if is_low_conf else "✅"
                                
                                app_logger.info(f"[DEBUG] {match_symbol} Alignment Match!{resync_tag}{conf_tag} Score: {match_result['score']:.2f}")
                                app_logger.info(f"[DEBUG]    Cursor: {match_result.get('cursor_position', 'N/A')}")
                                
                                # Handle multi-segment matches
                                all_matches = match_result.get('all_matches', [match_result])
                                app_logger.info(f"[DEBUG]    Matched {len(all_matches)} segment(s)")
                                
                                # Send all matched segments
                                for idx, seg_match in enumerate(all_matches):
                                    seg_low_conf = seg_match.get('low_confidence', False)
                                    conf_marker = " [?]" if seg_low_conf else ""
                                    app_logger.info(f"[DEBUG]    [{seg_match['index']}]{conf_marker} {seg_match['source'][:30]}... -> {seg_match['target'][:30]}...")
                                    
                                    # Send each segment as polished
                                    seg_id = current_segment_id if idx == 0 else f"{current_segment_id}-{idx}"
                                    await websocket.send_json({
                                        "type": "polished",
                                        "id": seg_id,
                                        "content": seg_match['source'],
                                        "translated": seg_match['target'],
                                        "low_confidence": seg_low_conf  # Frontend can style differently
                                    })
                                
                                alignment_success = True
                            else:
                                failures = script_aligner.consecutive_failures
                                app_logger.info(f"[DEBUG] ❌ Alignment completely failed for: '{corrected_text[:50]}...' (failures: {failures}/{script_aligner.MAX_CONSECUTIVE_FAILURES})")
                                if failures >= script_aligner.MAX_CONSECUTIVE_FAILURES:
                                    app_logger.info(f"[DEBUG] ⚠️ Next attempt will trigger GLOBAL RESYNC")
                        elif operation_mode == "alignment":
                            app_logger.warning(f"[DEBUG] ⚠️ Alignment mode active but no script loaded!")

                        # 2. Call LLM service asynchronously (Only if NOT in alignment mode)
                        # In alignment mode, if no match is found, we skip translation entirely
                        if not alignment_success and operation_mode != "alignment":
                            # Pass previous_context AND language settings
                            asyncio.create_task(polish_transcription_task(
                                current_segment_id, 
                                transcript_text, 
                                previous_context, 
                                source_lang,
                                target_lang,
                                websocket
                            ))
                        
                        # Update context for next segment
                        previous_context = transcript_text
                        
                        # Prepare for next segment
                        current_segment_id = str(uuid.uuid4())
                        last_partial_time = time.time()

                    else:
                        app_logger.info(f"Received empty transcription from ASR for [{current_segment_id}]. Clearing partial.")
                        # Send empty raw to finalize/clear the partial on frontend
                        await websocket.send_json({
                            "type": "raw",
                            "id": current_segment_id,
                            "content": "" 
                        })
                        # Reset ID anyway to prevent Partial ghosting if previous was noise
                        current_segment_id = str(uuid.uuid4())
                        last_partial_time = time.time()

    except WebSocketDisconnect:
        app_logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} disconnected.")
    except RuntimeError as e:
        # Starlette/FastAPI might raise RuntimeError on receive if disconnected
        if "disconnect message" in str(e):
            app_logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} disconnected (RuntimeError).")
        else:
            app_logger.error(f"WebSocket Runtime error: {e}", exc_info=True)
    except Exception as e:
        app_logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Cancel heartbeat task
        if heartbeat_task:
            heartbeat_task.cancel()
        
        # Update Meeting's duration stat
        if current_meeting_id:
            try:
                meeting_to_update = db.query(Meeting).filter(Meeting.id == current_meeting_id).first()
                if meeting_to_update:
                    # Calculate and store recording duration
                    if first_audio_time is not None:
                        meeting_to_update.duration = time.time() - first_audio_time
                        app_logger.info(f"Meeting {current_meeting_id} live duration updated: {meeting_to_update.duration:.1f}s")
                    db.commit()
            except Exception as e:
                app_logger.error(f"Error updating meeting state on disconnect: {e}")
        
        app_logger.info("WebSocket disconnect cleanup finished.")