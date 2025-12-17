from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

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

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, index=True)
    status = Column(Enum(MeetingStatus), default=MeetingStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    artifacts = relationship("Artifact", back_populates="meeting")

class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True, index=True)
    meeting_id = Column(String, ForeignKey("meetings.id"))
    file_path = Column(String)
    artifact_type = Column(Enum(ArtifactType))
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="artifacts")

class TaskStatus(Base):
    __tablename__ = "task_status"

    id = Column(String, primary_key=True, index=True)
    meeting_id = Column(String, ForeignKey("meetings.id"))
    task_name = Column(String)
    status = Column(String) # e.g., "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    meeting = relationship("Meeting")
