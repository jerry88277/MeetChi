"""
API Routes for Search, Tags, and Folders
PostgreSQL Full Text Search + Organization Features
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, text, desc
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid

# Import models
from app.models import Meeting, TranscriptSegment, Tag, Folder, meeting_tags
from app.database import get_db

router = APIRouter(prefix="/api/v1", tags=["Search & Organization"])


# ============================================
# Pydantic Models
# ============================================

class SearchResult(BaseModel):
    id: str
    title: str
    snippet: str
    rank: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResult]


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field("#6366f1", pattern=r'^#[0-9a-fA-F]{6}$')


class TagRead(BaseModel):
    id: str
    name: str
    color: str
    is_system: bool
    meeting_count: int = 0
    
    class Config:
        from_attributes = True


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: Optional[str] = None


class FolderRead(BaseModel):
    id: str
    name: str
    path: str
    parent_id: Optional[str]
    meeting_count: int = 0
    children_count: int = 0
    
    class Config:
        from_attributes = True


class MeetingMove(BaseModel):
    meeting_ids: List[str]
    folder_id: Optional[str] = None  # None = root


class MeetingTagUpdate(BaseModel):
    meeting_id: str
    tag_ids: List[str]


# ============================================
# Full Text Search Endpoints
# ============================================

@router.get("/search", response_model=SearchResponse)
async def search_meetings(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Search across meetings using LIKE (SQLite-compatible).
    Searches title, transcript_raw, and summary_json content.
    """
    like_pattern = f"%{q}%"
    
    results = db.execute(text("""
        SELECT 
            m.id,
            m.title,
            SUBSTR(COALESCE(m.transcript_raw, ''), 1, 200) as snippet,
            1.0 as rank,
            m.created_at
        FROM meetings m
        WHERE m.title LIKE :pattern
           OR m.transcript_raw LIKE :pattern
           OR m.summary_json LIKE :pattern
        ORDER BY m.created_at DESC
        LIMIT :limit OFFSET :offset
    """), {"pattern": like_pattern, "limit": limit, "offset": offset}).fetchall()
    
    # Get total count
    total = db.execute(text("""
        SELECT COUNT(*) FROM meetings 
        WHERE title LIKE :pattern
           OR transcript_raw LIKE :pattern
           OR summary_json LIKE :pattern
    """), {"pattern": like_pattern}).scalar()
    
    return SearchResponse(
        query=q,
        total=total or 0,
        results=[
            SearchResult(
                id=r.id,
                title=r.title,
                snippet=r.snippet or "",
                rank=r.rank,
                created_at=r.created_at
            ) for r in results
        ]
    )


@router.get("/search/segments")
async def search_segments(
    q: str = Query(..., min_length=1),
    meeting_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Search within transcript segments using LIKE (SQLite-compatible).
    Optionally filter by meeting_id.
    """
    like_pattern = f"%{q}%"
    
    query_str = """
        SELECT 
            ts.id,
            ts.meeting_id,
            ts.start_time,
            ts.end_time,
            ts.speaker,
            ts.content_raw,
            1.0 as rank
        FROM transcript_segments ts
        WHERE ts.content_raw LIKE :pattern
    """
    if meeting_id:
        query_str += " AND ts.meeting_id = :meeting_id"
    query_str += " ORDER BY ts.start_time ASC LIMIT :limit"
    
    params = {"pattern": like_pattern, "limit": limit}
    if meeting_id:
        params["meeting_id"] = meeting_id
    
    results = db.execute(text(query_str), params).fetchall()
    
    return {
        "query": q,
        "total": len(results),
        "segments": [
            {
                "id": r.id,
                "meeting_id": r.meeting_id,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "speaker": r.speaker,
                "text": r.content_raw,
                "rank": r.rank
            } for r in results
        ]
    }


# ============================================
# Tag Endpoints
# ============================================

@router.get("/tags", response_model=List[TagRead])
async def list_tags(db: Session = Depends(get_db)):
    """List all tags with meeting counts."""
    tags = db.query(
        Tag,
        func.count(meeting_tags.c.meeting_id).label('meeting_count')
    ).outerjoin(meeting_tags).group_by(Tag.id).all()
    
    return [
        TagRead(
            id=t.Tag.id,
            name=t.Tag.name,
            color=t.Tag.color,
            is_system=t.Tag.is_system,
            meeting_count=t.meeting_count
        ) for t in tags
    ]


@router.post("/tags", response_model=TagRead)
async def create_tag(tag_data: TagCreate, db: Session = Depends(get_db)):
    """Create a new user tag."""
    # Check if tag exists
    existing = db.query(Tag).filter(Tag.name == tag_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag already exists")
    
    tag = Tag(
        id=str(uuid.uuid4()),
        name=tag_data.name,
        color=tag_data.color,
        is_system=False
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    
    return TagRead(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        is_system=tag.is_system,
        meeting_count=0
    )


@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: str, db: Session = Depends(get_db)):
    """Delete a user tag (cannot delete system tags)."""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    if tag.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system tags")
    
    db.delete(tag)
    db.commit()
    return {"message": "Tag deleted"}


@router.post("/meetings/{meeting_id}/tags")
async def update_meeting_tags(
    meeting_id: str,
    tag_ids: List[str],
    db: Session = Depends(get_db)
):
    """Update tags for a meeting."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    # Get tags
    tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
    
    # Update relationship
    meeting.tags = tags
    db.commit()
    
    return {"message": "Tags updated", "tag_count": len(tags)}


# ============================================
# Folder Endpoints
# ============================================

@router.get("/folders", response_model=List[FolderRead])
async def list_folders(
    parent_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List folders at a given level (None = root)."""
    query = db.query(Folder)
    if parent_id:
        query = query.filter(Folder.parent_id == parent_id)
    else:
        query = query.filter(Folder.parent_id.is_(None))
    
    folders = query.order_by(Folder.name).all()
    
    result = []
    for f in folders:
        meeting_count = db.query(Meeting).filter(Meeting.folder_id == f.id).count()
        children_count = db.query(Folder).filter(Folder.parent_id == f.id).count()
        result.append(FolderRead(
            id=f.id,
            name=f.name,
            path=f.path,
            parent_id=f.parent_id,
            meeting_count=meeting_count,
            children_count=children_count
        ))
    
    return result


@router.post("/folders", response_model=FolderRead)
async def create_folder(folder_data: FolderCreate, db: Session = Depends(get_db)):
    """Create a new folder."""
    # Get parent path
    parent_path = "/"
    if folder_data.parent_id:
        parent = db.query(Folder).filter(Folder.id == folder_data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        parent_path = parent.path
    
    folder = Folder(
        id=str(uuid.uuid4()),
        name=folder_data.name,
        parent_id=folder_data.parent_id,
        path=f"{parent_path.rstrip('/')}/{folder_data.name}"
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    
    return FolderRead(
        id=folder.id,
        name=folder.name,
        path=folder.path,
        parent_id=folder.parent_id,
        meeting_count=0,
        children_count=0
    )


@router.delete("/folders/{folder_id}")
async def delete_folder(folder_id: str, db: Session = Depends(get_db)):
    """Delete a folder (moves meetings to root)."""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Move meetings to root
    db.query(Meeting).filter(Meeting.folder_id == folder_id).update(
        {"folder_id": None},
        synchronize_session=False
    )
    
    # Delete folder
    db.delete(folder)
    db.commit()
    
    return {"message": "Folder deleted"}


@router.post("/meetings/move")
async def move_meetings(move_data: MeetingMove, db: Session = Depends(get_db)):
    """Move meetings to a folder."""
    # Validate folder exists
    if move_data.folder_id:
        folder = db.query(Folder).filter(Folder.id == move_data.folder_id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
    
    # Update meetings
    updated = db.query(Meeting).filter(
        Meeting.id.in_(move_data.meeting_ids)
    ).update(
        {"folder_id": move_data.folder_id},
        synchronize_session=False
    )
    
    db.commit()
    
    return {"message": f"Moved {updated} meetings"}


@router.get("/folders/{folder_id}/meetings")
async def list_folder_meetings(
    folder_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List meetings in a folder."""
    meetings = db.query(Meeting).filter(
        Meeting.folder_id == folder_id
    ).order_by(desc(Meeting.created_at)).offset(skip).limit(limit).all()
    
    return {
        "folder_id": folder_id,
        "total": len(meetings),
        "meetings": [
            {
                "id": m.id,
                "title": m.title,
                "created_at": m.created_at,
                "status": m.status.value if m.status else None
            } for m in meetings
        ]
    }
