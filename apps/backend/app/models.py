from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, Float, Boolean, Table, Index, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
# TSVECTOR removed — SQLite compatible
from datetime import datetime
import enum
import uuid # Import uuid for UUID type
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class MeetingStatus(enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PENDING = "PENDING"
    REFINING = "REFINING"  # Offline ASR refinement in progress (Plan B)

class ArtifactType(enum.Enum):
    AUDIO = "AUDIO"
    TRANSCRIPT_TXT = "TRANSCRIPT_TXT"
    TRANSCRIPT_SRT = "TRANSCRIPT_SRT"
    TRANSCRIPT_JSON = "TRANSCRIPT_JSON"
    SUMMARY_DOCX = "SUMMARY_DOCX"

# ============================================
# Enums for Access Control
# ============================================
class ParticipantRole(enum.Enum):
    OWNER       = "owner"        # 上傳者，可刪除、授權他人
    PARTICIPANT = "participant"  # 出席者，可讀取
    VIEWER      = "viewer"       # 事後被授權，唯讀

class AccessSource(enum.Enum):
    UPLOAD      = "upload"       # 自己上傳 (B1)
    PARTICIPANT = "participant"  # 出席者 (A1/A2)
    GRANTED     = "granted"      # 被授予 (B2)

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
# User Model (AD Account Registry)
# ============================================
class User(Base):
    """AD 帳號登錄表。以 userPrincipalName (UPN) 作為唯一識別符。"""
    __tablename__ = "users"

    id            = Column(String(36),  primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    ad_upn        = Column(String(255), nullable=False, unique=True, index=True)  # user@company.com
    display_name  = Column(String(255), nullable=True)
    department    = Column(String(255), nullable=True)   # 從 AD 同步，供未來群組存取用
    is_admin      = Column(Boolean,     nullable=False, default=False)  # 系統管理員可存取所有會議
    created_at    = Column(DateTime,    default=datetime.utcnow)
    last_login_at = Column(DateTime,    nullable=True)

    # Relationships
    owned_meetings      = relationship("Meeting", back_populates="owner", foreign_keys="Meeting.owner_upn")
    meeting_access      = relationship("MeetingParticipant", back_populates="user", foreign_keys="MeetingParticipant.user_upn")
    granted_access      = relationship("MeetingParticipant", back_populates="granter", foreign_keys="MeetingParticipant.granted_by_upn")

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

    # Access Control: 上傳者/擁有者 (對應 users.ad_upn)
    owner_upn = Column(String(255), ForeignKey("users.ad_upn"), nullable=True, index=True)

    # Store full transcripts and summary as text/JSON strings
    transcript_raw = Column(Text, nullable=True)
    transcript_polished = Column(Text, nullable=True)
    summary_json = Column(Text, nullable=True) # Structured summary in JSON format
    
    # Phase 8.1: Speaker mappings (JSON) — stores { "Speaker_0": { "display_name": "李經理", "role": "客戶", "color": "#5FB7AC" } }
    speaker_mappings = Column(Text, nullable=True)
    
    # Custom prompt for user-defined summarization instructions
    custom_prompt = Column(Text, nullable=True)
    
    # pgvector embedding for future semantic search
    summary_embedding = Column(Vector(768), nullable=True)
    
    # Full Text Search removed (PostgreSQL-only TSVECTOR)
    # Can be reimplemented with SQLite FTS5 if needed

    # Relationships
    folder              = relationship("Folder", back_populates="meetings")
    tags                = relationship("Tag", secondary=meeting_tags, back_populates="meetings")
    artifacts           = relationship("Artifact", back_populates="meeting")
    transcript_segments = relationship("TranscriptSegment", back_populates="meeting", order_by="TranscriptSegment.order")
    task_statuses       = relationship("TaskStatus", back_populates="meeting")
    owner               = relationship("User", back_populates="owned_meetings", foreign_keys=[owner_upn])
    participants        = relationship("MeetingParticipant", back_populates="meeting", cascade="all, delete-orphan")

# GIN Index removed (PostgreSQL-only)


# ============================================
# MeetingParticipant Model (Access Control Join Table)
# ============================================
class MeetingParticipant(Base):
    """會議存取控制關聯表。每一筆記錄代表「某人擁有某場會議的某種存取權」。"""
    __tablename__ = "meeting_participants"

    id             = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    meeting_id     = Column(String(36), ForeignKey("meetings.id",  ondelete="CASCADE"), nullable=False)
    user_upn       = Column(String(255), ForeignKey("users.ad_upn", ondelete="CASCADE"), nullable=False)

    # 存取角色 (MECE)
    role           = Column(Enum(ParticipantRole), nullable=False, default=ParticipantRole.PARTICIPANT)
    # 存取來源（稽核軌跡）
    access_source  = Column(Enum(AccessSource),    nullable=False, default=AccessSource.PARTICIPANT)

    # 稽核欄位
    granted_at     = Column(DateTime,   nullable=False, default=datetime.utcnow)
    granted_by_upn = Column(String(255), ForeignKey("users.ad_upn"), nullable=True)  # B2 授權時填入

    # Relationships
    meeting = relationship("Meeting",  back_populates="participants", foreign_keys=[meeting_id])
    user    = relationship("User",     back_populates="meeting_access", foreign_keys=[user_upn])
    granter = relationship("User",     back_populates="granted_access", foreign_keys=[granted_by_upn])

    # 複合唯一：同一個人對同一場會議只有一筆記錄
    __table_args__ = (
        Index("idx_mp_user_upn",    "user_upn"),
        Index("idx_mp_meeting_id",  "meeting_id"),
        Index("idx_mp_upn_meeting", "user_upn", "meeting_id"),
        # 複合唯一約束
        Index("uq_meeting_participant", "meeting_id", "user_upn", unique=True),
    )


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
    
    # pgvector embedding for future semantic search
    content_embedding = Column(Vector(768), nullable=True)
    
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

# Phase 8.2: User-created summary templates
class SummaryTemplateModel(Base):
    __tablename__ = "summary_templates"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(30), default="custom")
    icon = Column(String(30), default="FileText")
    color = Column(String(30), default="brand-cta")
    sections = Column(JSON, nullable=True)  # List of section dicts
    tags = Column(JSON, nullable=True)  # List of tag strings
    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Phase D: Summary version history for multi-template comparison
class SummaryVersion(Base):
    __tablename__ = "summary_versions"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=False, index=True)
    template_name = Column(String(50), nullable=False, default="general")
    summary_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", backref="summary_versions")


# ============================================
# Feedback Report (Sprint 2d / PR22)
# ============================================
# user 在前端任何頁面點「回報問題」 → POST /api/v1/feedback 寫進這個表。
# 設計依先前訪談結果：階段 1 必填 3 項，階段 2 可選；auto-attached metadata
# 由前端送出（測試環境收集無顧慮）。
class FeedbackReport(Base):
    """User feedback 回報記錄。"""
    __tablename__ = "feedback_reports"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # 階段 1 必填
    user_upn = Column(String(255), nullable=False, index=True)
    issue_type = Column(
        String(50), nullable=False, index=True,
        comment="transcript_inaccurate / summary_wrong / ui_clunky / system_error / other",
    )
    summary = Column(Text, nullable=False, comment="一句話描述（10-100 字）")
    severity = Column(
        String(20), nullable=False,
        comment="minor (繞得過) / workaround (有解) / blocker (完全擋住)",
    )

    # 階段 2 可選（補充細節，讓工程師更快重現）
    expected = Column(Text, nullable=True, comment="使用者期待的結果")
    actual = Column(Text, nullable=True, comment="使用者實際看到的結果")
    repro_steps = Column(Text, nullable=True, comment="重現步驟")
    frequency = Column(
        String(20), nullable=True,
        comment="first / rare (10%-) / common (10-50%) / always",
    )
    attachment_url = Column(Text, nullable=True, comment="GCS 路徑 or null")

    # Auto-attached metadata（前端送）
    meeting_id = Column(String(36), ForeignKey("meetings.id"), nullable=True, index=True)
    page_url = Column(Text, nullable=True)
    browser_info = Column(Text, nullable=True)
    session_id = Column(String(64), nullable=True)
    frontend_version = Column(String(20), nullable=True)
    backend_version = Column(String(20), nullable=True)
    console_errors = Column(JSON, nullable=True)

    # 後續追蹤狀態（admin 用）
    status = Column(
        String(20), nullable=False, default="open", index=True,
        comment="open / in_progress / fixed / wontfix / duplicate",
    )
    assigned_to = Column(String(255), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    notify_user = Column(Boolean, nullable=False, default=True)
    admin_notes = Column(Text, nullable=True)

    # 時間軸
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meeting = relationship("Meeting", foreign_keys=[meeting_id])

    __table_args__ = (
        Index("idx_feedback_user_upn", "user_upn"),
        Index("idx_feedback_status", "status"),
        Index("idx_feedback_created", "created_at"),
        Index("idx_feedback_issue_type_status", "issue_type", "status"),
    )