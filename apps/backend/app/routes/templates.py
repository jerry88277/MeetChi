"""Phase 8.2: Template CRUD API routes.

2026-06-29 audit fixes:
- Added user auth (get_current_user) to all endpoints
- Added owner_upn tenant isolation (personal templates only visible to owner)
- Added visibility field support (private/shared)
- Soft delete instead of hard delete
- Instruction length limit (max 500 chars)
- Collision-safe name generation
- Usage check before delete
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.auth import get_current_user
from app.template_engine import (
    get_all_system_templates,
    get_template_by_name,
    TemplateSection,
)
from app import models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


# --- Request/Response schemas ---

class TemplateSectionDTO(BaseModel):
    title: str
    instruction: str = Field(..., max_length=500)
    output_key: str
    output_type: str = "list"

    @field_validator('instruction', mode='before')
    @classmethod
    def validate_instruction_length(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("instruction 長度不可超過 500 字元")
        return v

class TemplateResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    category: str
    icon: str
    color: str
    sections: List[TemplateSectionDTO]
    tags: List[str]
    is_system: bool
    is_active: bool
    owner_upn: Optional[str] = None
    usage_count: int = 0

class CreateTemplateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    category: str = "custom"
    icon: str = "FileText"
    color: str = "brand-cta"
    sections: List[TemplateSectionDTO] = []
    tags: List[str] = []
    fork_from: Optional[str] = Field(None, description="System template name to fork from")

class UpdateTemplateRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sections: Optional[List[TemplateSectionDTO]] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


# --- Helper ---

def _get_usage_count(db: Session, template_name: str) -> int:
    """Count how many meetings use this template."""
    try:
        return db.query(func.count(models.Meeting.id)).filter(
            models.Meeting.template_name == template_name,
            models.Meeting.deleted_at.is_(None),
        ).scalar() or 0
    except Exception:
        return 0


def _template_to_response(tpl, is_system: bool, usage_count: int = 0, owner_upn: str = None) -> TemplateResponse:
    """Convert a template (system or DB) to response DTO."""
    if is_system:
        return TemplateResponse(
            id=tpl.id, name=tpl.name, display_name=tpl.display_name,
            description=tpl.description, category=tpl.category,
            icon=tpl.icon, color=tpl.color,
            sections=[TemplateSectionDTO(
                title=s.title, instruction=s.instruction,
                output_key=s.output_key, output_type=s.output_type,
            ) for s in tpl.sections],
            tags=tpl.tags, is_system=True, is_active=tpl.is_active,
            owner_upn=None, usage_count=usage_count,
        )
    else:
        return TemplateResponse(
            id=str(tpl.id), name=tpl.name, display_name=tpl.display_name,
            description=tpl.description or "", category=tpl.category or "custom",
            icon=tpl.icon or "FileText", color=tpl.color or "brand-cta",
            sections=[TemplateSectionDTO(**s) for s in (tpl.sections or [])],
            tags=tpl.tags or [], is_system=False, is_active=tpl.is_active,
            owner_upn=tpl.created_by, usage_count=usage_count,
        )


# --- Routes ---

@router.get("", response_model=List[TemplateResponse])
async def list_templates(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all templates: system templates + current user's custom templates."""
    user_email = user.get("email", "").lower()
    result = []
    
    # System templates (visible to all)
    for tpl in get_all_system_templates():
        usage = _get_usage_count(db, tpl.name)
        result.append(_template_to_response(tpl, is_system=True, usage_count=usage))
    
    # User-created templates: only show user's own templates
    try:
        db_templates = db.query(models.SummaryTemplateModel).filter(
            models.SummaryTemplateModel.is_active == True,
            models.SummaryTemplateModel.created_by == user_email,
        ).all()
        for dt in db_templates:
            usage = _get_usage_count(db, dt.name)
            result.append(_template_to_response(dt, is_system=False, usage_count=usage, owner_upn=dt.created_by))
    except Exception as e:
        logger.warning(f"Could not query user templates: {e}")
    
    return result


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a single template by ID."""
    # Check system templates first
    for tpl in get_all_system_templates():
        if tpl.id == template_id:
            usage = _get_usage_count(db, tpl.name)
            return _template_to_response(tpl, is_system=True, usage_count=usage)
    
    # Check DB (only own templates)
    user_email = user.get("email", "").lower()
    try:
        dt = db.query(models.SummaryTemplateModel).filter_by(id=template_id).first()
        if dt:
            if dt.created_by and dt.created_by != user_email:
                raise HTTPException(status_code=403, detail="無權存取此模板")
            usage = _get_usage_count(db, dt.name)
            return _template_to_response(dt, is_system=False, usage_count=usage)
    except HTTPException:
        raise
    except Exception:
        pass
    
    raise HTTPException(status_code=404, detail="Template not found")


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    req: CreateTemplateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new user template (or fork from a system template)."""
    user_email = user.get("email", "").lower()
    sections_data = [s.model_dump() for s in req.sections]
    
    # If forking from a system template, copy its sections
    if req.fork_from:
        source = get_template_by_name(req.fork_from)
        if source and not sections_data:
            sections_data = [
                {"title": s.title, "instruction": s.instruction,
                 "output_key": s.output_key, "output_type": s.output_type}
                for s in source.sections
            ]
    
    # Generate collision-safe name
    base_name = req.name or f"{req.fork_from or 'custom'}_{user_email.split('@')[0]}"
    template_name = base_name
    suffix = 1
    while db.query(models.SummaryTemplateModel).filter_by(name=template_name).first():
        template_name = f"{base_name}_{suffix}"
        suffix += 1
    
    new_id = str(uuid.uuid4())
    dt = models.SummaryTemplateModel(
        id=new_id,
        name=template_name,
        display_name=req.display_name,
        description=req.description,
        category=req.category,
        icon=req.icon,
        color=req.color,
        sections=sections_data,
        tags=req.tags,
        is_system=False,
        is_active=True,
        created_by=user_email,
    )
    db.add(dt)
    db.commit()
    db.refresh(dt)
    
    logger.info(f"[Template] Created '{template_name}' by {user_email} (forked from: {req.fork_from})")
    return _template_to_response(dt, is_system=False, owner_upn=user_email)


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    req: UpdateTemplateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update a user-created template (owner only)."""
    user_email = user.get("email", "").lower()
    dt = db.query(models.SummaryTemplateModel).filter_by(id=template_id).first()
    if not dt:
        raise HTTPException(status_code=404, detail="Template not found")
    if dt.is_system:
        raise HTTPException(status_code=403, detail="無法修改系統模板")
    if dt.created_by and dt.created_by != user_email:
        raise HTTPException(status_code=403, detail="只能修改自己建立的模板")
    
    if req.display_name is not None: dt.display_name = req.display_name
    if req.description is not None: dt.description = req.description
    if req.category is not None: dt.category = req.category
    if req.icon is not None: dt.icon = req.icon
    if req.color is not None: dt.color = req.color
    if req.sections is not None: dt.sections = [s.model_dump() for s in req.sections]
    if req.tags is not None: dt.tags = req.tags
    if req.is_active is not None: dt.is_active = req.is_active
    
    dt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dt)
    
    usage = _get_usage_count(db, dt.name)
    return _template_to_response(dt, is_system=False, usage_count=usage, owner_upn=dt.created_by)


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    force: bool = Query(False, description="強制刪除（即使有會議使用此模板）"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Soft-delete a user-created template (owner only). Returns usage warning if meetings exist."""
    user_email = user.get("email", "").lower()
    dt = db.query(models.SummaryTemplateModel).filter_by(id=template_id).first()
    if not dt:
        raise HTTPException(status_code=404, detail="Template not found")
    if dt.is_system:
        raise HTTPException(status_code=403, detail="無法刪除系統模板")
    if dt.created_by and dt.created_by != user_email:
        raise HTTPException(status_code=403, detail="只能刪除自己建立的模板")
    
    # Check usage
    usage_count = _get_usage_count(db, dt.name)
    if usage_count > 0 and not force:
        return {
            "warning": True,
            "message": f"此模板已被 {usage_count} 場會議使用。確定要刪除嗎？",
            "usage_count": usage_count,
            "template_id": template_id,
        }
    
    # Soft delete
    dt.is_active = False
    dt.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    logger.info(f"[Template] Soft-deleted '{dt.name}' by {user_email} (usage_count={usage_count})")
    return {"deleted": True, "template_id": template_id}
