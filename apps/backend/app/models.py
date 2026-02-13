from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, Float, Boolean, Table, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
# TSVECTOR removed — SQLite compatible
from datetime import datetime
import enum
import uuid # Import uuid for UUID type

Base = declarative_base()

class MeetingStatus(enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PENDING = "PENDING"

class ArtifactType(enum.Enum):
    AUDIO = "AUDIO"
    TRANSCRIPT_TXT = "TRANSCRIPT_TXT"
    TRANSCRIPT_SRT = "TRANSCRIPT_SRT"
    TRANSCRIPT_JSON = "TRANSCRIPT_JSON"
    SUMMARY_DOCX = "SUMMARY_DOCX"

# ============================================
# Many-to-Many Association Table: Meeting <-> Tag
# ============================================
meeting_tags = Table(
    'meeting_tags',
    Base.metadata,
    Column('meeting_id', String(36), ForeignKey('meetings.id'), primary_key=True),
    Column('tag_id', String(36), ForeignKey('tags.id'), primary_key=True)
)

# ============================================
# Folder Model (for hierarchical organization)
# ============================================
class Folder(Base):
    __tablename__ = "folders"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    parent_id = Column(String(36), ForeignKey("folders.id"), nullable=True)  # Self-referential for hierarchy
    path = Column(String(1000), nullable=False, default="/")  # Full path like "/Sales/2024/Q1"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    parent = relationship("Folder", remote_side=[id], backref="children")
    meetings = relationship("Meeting", back_populates="folder")

# ============================================
# Tag Model (for flexible labeling)
# ============================================
class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    color = Column(String(7), default="#6366f1")  # Hex color for UI
    is_system = Column(Boolean, default=False)  # True for predefined tags
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    meetings = relationship("Meeting", secondary=meeting_tags, back_populates="tags")

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4())) # Use String for UUID
    title = Column(String, index=True, default="Untitled Meeting")
    status = Column(Enum(MeetingStatus), default=MeetingStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    duration = Column(Float, nullable=True) # Meeting duration in seconds
    audio_url = Column(String, nullable=True) # URL to the raw audio file (e.g., GCS)
    language = Column(String(10), default="zh") # Main language of the meeting (e.g., "zh", "en")
    template_name = Column(String(50), default="general") # Template used for summarization
    
    # Folder organization
    folder_id = Column(String(36), ForeignKey("folders.id"), nullable=True)

    # Store full transcripts and summary as text/JSON strings
    transcript_raw = Column(Text, nullable=True)
    transcript_polished = Column(Text, nullable=True)
    summary_json = Column(Text, nullable=True) # Structured summary in JSON format
    
    # Full Text Search removed (PostgreSQL-only TSVECTOR)
    # Can be reimplemented with SQLite FTS5 if needed

    # Relationships
    folder = relationship("Folder", back_populates="meetings")
    tags = relationship("Tag", secondary=meeting_tags, back_populates="meetings")
    artifacts = relationship("Artifact", back_populates="meeting")
    transcript_segments = relationship("TranscriptSegment", back_populates="meeting", order_by="TranscriptSegment.order") # Add relationship
    task_statuses = relationship("TaskStatus", back_populates="meeting")

# GIN Index removed (PostgreSQL-only)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"))
    order = Column(Integer, index=True) # Order of the segment in the transcript
    start_time = Column(Float)
    end_time = Column(Float)
    speaker = Column(String(50), nullable=True) # Speaker label (e.g., "Speaker A", "Jerry")
    content_raw = Column(Text)
    content_polished = Column(Text, nullable=True)
    content_translated = Column(Text, nullable=True)
    is_final = Column(Boolean, default=False) # Whether this segment is a final transcription
    
    # FTS removed (PostgreSQL-only TSVECTOR)

    meeting = relationship("Meeting", back_populates="transcript_segments") # Add back_populates

# GIN Index removed (PostgreSQL-only)


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"))
    file_path = Column(String)
    artifact_type = Column(Enum(ArtifactType))
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="artifacts")

class TaskStatus(Base):
    __tablename__ = "task_status"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"))
    task_name = Column(String)
    status = Column(String) # e.g., "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="task_statuses") # Add back_populates