from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware # Import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
import os
import io
import asyncio
import numpy as np
import logging
import httpx # For async HTTP requests
import uuid # For generating unique IDs
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Import models to ensure they are registered with SQLAlchemy Base
from app.models import Base, Meeting, Artifact, TaskStatus
from app.vad import VADAudioBuffer # Import VAD Logic

# Import ASR transcription function
# With PYTHONPATH="apps/backend", 'scripts' is a top-level package
from scripts.transcribe_sprint0 import get_transcription, load_asr_model, logger as asr_logger 

# Database Configuration
# Default to a local SQLite for basic testing if DATABASE_URL is not set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:5000") # New LLM Service URL
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Celery App Import
from app.celery_app import celery_app
from app.tasks import generate_meeting_minutes

# FastAPI App
app = FastAPI()

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ... (Logging configuration remains same) ...

# --- API Endpoints ---

@app.post("/api/v1/meetings/{meeting_id}/generate-summary")
def trigger_summary_generation(meeting_id: str, template_type: str = "general", db: Session = Depends(get_db)):
    """
    Trigger background task to generate meeting minutes.
    """
    # In a real app, verify meeting exists first
    task = generate_meeting_minutes.delay(meeting_id, template_type)
    return {"message": "Summary generation started", "task_id": task.id}

@app.get("/api/v1/meetings")
def list_meetings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    List historical meetings.
    """
    # Placeholder: return mock data or query DB
    # meetings = db.query(Meeting).offset(skip).limit(limit).all()
    return []

@app.get("/api/v1/meetings/{meeting_id}")
def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """
    Get meeting details including transcript and summary.
    """
    # Placeholder
    return {"id": meeting_id, "title": "Mock Meeting", "transcript": [], "summary": {}}



# Ensure log directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
os.makedirs(LOG_DIR, exist_ok=True)

# Create a root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clear existing handlers to prevent duplicate logs (e.g. from Uvicorn's default config)
if logger.hasHandlers():
    logger.handlers.clear()

# Formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# 1. Stream Handler (Console)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# 2. File Handler (Rotating by day)
log_filename = os.path.join(LOG_DIR, "backend.log")
file_handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, backupCount=7, encoding="utf-8")
file_handler.suffix = "%Y-%m-%d" # Suffix for rotated files: backend.log.2023-10-27
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

app_logger = logging.getLogger(__name__)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Load ASR model during startup
@app.on_event("startup")
async def on_startup():
    app_logger.info("Application startup event triggered.")
    # Create database tables if they don't exist (only for SQLite or if DB user has rights)
    # For Neon, tables will likely be managed externally or by alembic migrations.
    Base.metadata.create_all(bind=engine)
    app_logger.info("Database tables checked/created.")
    
    # Pre-load ASR model. Use asyncio.to_thread for blocking call in async context
    app_logger.info("Pre-loading ASR model...")
    try:
        await asyncio.to_thread(load_asr_model)
        app_logger.info("ASR model pre-loaded successfully.")
    except Exception as e:
        app_logger.critical(f"Failed to pre-load ASR model during startup: {e}")
        # Depending on criticality, might raise exception to prevent app startup
        raise RuntimeError("ASR model pre-loading failed. Cannot start application.") from e

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    try:
        # Try to query something simple to test connection
        # db.execute("SELECT 1") # Use session.execute for SQLAlchemy 2.0
        db.scalar("SELECT 1") # Use scalar for simple select 1
        return {"message": "Database connection successful!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")


import time # Import time for partial transcription throttling
import json # Import json for config parsing

async def polish_transcription_task(segment_id: str, transcript_text: str, previous_context: str, source_lang: str, target_lang: str, websocket: WebSocket):
    """
    Async task to call LLM service for polishing and send result back to WebSocket.
    Includes previous_context for better semantic accuracy.
    """
    try:
        async with httpx.AsyncClient() as client:
            llm_response = await client.post(
                f"{LLM_SERVICE_URL}/polish",
                json={
                    "text": transcript_text,
                    "previous_context": previous_context,
                    "source_lang": source_lang,
                    "target_lang": target_lang
                },
                timeout=30.0 
            )
            llm_response.raise_for_status() 
            polished_data = llm_response.json()
            
            # New format: {'refined': '...', 'translated': '...'}
            # Fallback to 'polished_text' or raw text if keys missing
            refined_text = polished_data.get("refined", polished_data.get("polished_text", transcript_text))
            translated_text = polished_data.get("translated", "")

            # DEFENSIVE CODING: Ensure these are strings, not dicts
            if isinstance(refined_text, dict):
                refined_text = refined_text.get('content', str(refined_text))
            if isinstance(translated_text, dict):
                translated_text = translated_text.get('content', str(translated_text))
            
            refined_text = str(refined_text)
            translated_text = str(translated_text)

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
async def websocket_transcribe(websocket: WebSocket):
    await websocket.accept()
    app_logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} connected for transcription.")

    # Initialize VAD Buffer (Defaults from vad.py: 5.0s max)
    RATE = 16000
    vad_buffer = VADAudioBuffer(
        sample_rate=RATE, 
        silence_threshold=0.4, 
        min_silence_duration=0.8, 
        max_duration=3
    )
    
    # Pseudo-streaming state
    last_partial_time = time.time()
    current_segment_id = str(uuid.uuid4())
    previous_context = "" # Store the last finalized transcript for context
    
    # --- Overlapping Window Buffer ---
    # Store history of processed audio to prepend to next segment
    OVERLAP_DURATION_SECONDS = 0.2 # How much previous audio to overlap
    last_flushed_segment_np = np.array([], dtype=np.float32) # Store the last VAD-flushed segment
    
    # Language Configuration (Default: ZH -> EN)
    source_lang = "zh"
    target_lang = "en"
    
    # Custom Initial Prompt from Frontend
    custom_initial_prompt = ""
    
    first_audio_time = None # Track time of first audio packet

    try:
        while True:
            # Receive message (can be text or bytes)
            message = await websocket.receive()
            
            # 1. Handle Configuration Messages (Text)
            if "text" in message:
                try:
                    config = json.loads(message["text"])
                    if config.get("type") == "config":
                        source_lang = config.get("source_lang", source_lang)
                        target_lang = config.get("target_lang", target_lang)
                        custom_initial_prompt = config.get("initial_prompt", "")
                        app_logger.info(f"Config updated: {source_lang} -> {target_lang} | Prompt len: {len(custom_initial_prompt)}")
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

            # --- Partial Transcription (Every 2.0s) ---
            now = time.time()
            if not audio_bytes and (now - last_partial_time) > 2.0:
                snapshot_bytes = vad_buffer.snapshot()
                if snapshot_bytes:
                    snapshot_np = np.frombuffer(snapshot_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    # Only transcribe if we have at least 1s of audio to avoid noise hallucinations
                    if snapshot_np.size > 16000:
                        # Use previous_context as initial_prompt for ASR consistency
                        combined_prompt = f"{custom_initial_prompt} {previous_context}".strip()
                        partial_text = await asyncio.to_thread(get_transcription, snapshot_np, source_lang, combined_prompt)
                        # Filter extremely short partials
                        if partial_text and len(partial_text.strip()) > 1:
                            await websocket.send_json({
                                "type": "partial",
                                "id": current_segment_id,
                                "content": partial_text
                            })
                        last_partial_time = now

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
                        # Add a timeout for ASR transcription to prevent service hang
                        # Longer timeout (e.g., 10s) to accommodate potentially slow ASR or longer segments
                        transcript_text = await asyncio.wait_for(
                            asyncio.to_thread(get_transcription, audio_for_transcription, source_lang, combined_prompt),
                            timeout=10.0 
                        )
                    except asyncio.TimeoutError:
                        app_logger.error(f"ASR transcription timed out for segment {current_segment_id}. Skipping segment.")
                        transcript_text = "" # Treat as empty on timeout
                    except Exception as e:
                        app_logger.error(f"Error during ASR transcription for segment {current_segment_id}: {e}", exc_info=True)
                        transcript_text = "" # Treat as empty on error
                    
                    if transcript_text:
                        app_logger.info(f"Raw Transcription [{current_segment_id}]: {transcript_text}")

                        # 1. Send raw transcript (Finalize the segment)
                        await websocket.send_json({
                            "type": "raw",
                            "id": current_segment_id,
                            "content": transcript_text
                        })

                        # 2. Call LLM service asynchronously (Non-blocking)
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
                        app_logger.debug("Received empty transcription from ASR.")
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
        app_logger.info(f"Closing WebSocket connection for {websocket.client.host}:{websocket.client.port}.")