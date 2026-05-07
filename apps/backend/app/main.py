from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
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
from app.asr_helpers import load_asr_model

# Gemini Setup handled in llm_utils







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

from app.schemas import (
    TranscriptSegmentRead,
    TranscriptSegmentCreate,
    MeetingRead,
    MeetingCreate,
    SummarizeRequestModel,
    SummarizeResponseModel,
    RegenerateSummaryRequest,
    SpeakerMappingEntry,
    SpeakerMappingUpdate,
)


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
