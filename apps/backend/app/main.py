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
        
        # BACKFILL: Find meetings with no participants and bind to their owner_upn.
        # 2026-06-08 fix: previously hardcoded 'test@company.com' which broke RAG access
        # control — users querying with real UPN couldn't see their own meetings.
        # Now we use the meeting's owner_upn as the participant so RAG JOIN works correctly.
        conn.execute(text("""
            INSERT INTO users (id, ad_upn, display_name, is_admin)
            SELECT gen_random_uuid()::varchar(36), m.owner_upn,
                   split_part(m.owner_upn, '@', 1), false
            FROM meetings m
            WHERE m.owner_upn IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM users u WHERE u.ad_upn = m.owner_upn)
            ON CONFLICT (ad_upn) DO NOTHING;
        """))

        conn.execute(text("""
            INSERT INTO meeting_participants (id, meeting_id, user_upn, role, access_source, granted_at)
            SELECT gen_random_uuid()::varchar(36), m.id, m.owner_upn, 'owner', 'upload', NOW()
            FROM meetings m
            WHERE m.owner_upn IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM meeting_participants mp WHERE mp.meeting_id = m.id
            )
            ON CONFLICT DO NOTHING;
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
    "https://meetchi-frontend-705495828555.asia-southeast1.run.app",
    "https://meetchi-frontend-wfqjx2j42q-as.a.run.app",
    "https://meetchi-frontend-atro34poxq-as.a.run.app",
    "https://meetchi-frontend-315688033208.asia-southeast1.run.app",
    "https://meetchi.chimei.com.tw",  # LB custom domain（未來）
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
