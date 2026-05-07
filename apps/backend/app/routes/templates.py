"""Phase 8.2: Template CRUD API routes."""
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
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
    instruction: str
    output_key: str
    output_type: str = "list"

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

class CreateTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
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


# --- Routes ---

@router.get("", response_model=List[TemplateResponse])
async def list_templates(db: Session = Depends(get_db)):
    """List all templates (system + user-created)."""
    result = []
    
    # System templates
    for tpl in get_all_system_templates():
        result.append(TemplateResponse(
            id=tpl.id,
            name=tpl.name,
            display_name=tpl.display_name,
            description=tpl.description,
            category=tpl.category,
            icon=tpl.icon,
            color=tpl.color,
            sections=[TemplateSectionDTO(
                title=s.title,
                instruction=s.instruction,
                output_key=s.output_key,
                output_type=s.output_type,
            ) for s in tpl.sections],
            tags=tpl.tags,
            is_system=True,
            is_active=tpl.is_active,
        ))
    
    # User-created templates from DB
    try:
        db_templates = db.query(models.SummaryTemplateModel).filter(
            models.SummaryTemplateModel.is_active == True
        ).all()
        for dt in db_templates:
            sections_data = dt.sections or []
            result.append(TemplateResponse(
                id=str(dt.id),
                name=dt.name,
                display_name=dt.display_name,
                description=dt.description or "",
                category=dt.category or "custom",
                icon=dt.icon or "FileText",
                color=dt.color or "brand-cta",
                sections=[TemplateSectionDTO(**s) for s in sections_data],
                tags=dt.tags or [],
                is_system=False,
                is_active=dt.is_active,
            ))
    except Exception as e:
        # DB table may not exist yet — gracefully degrade
        logger.warning(f"Could not query user templates: {e}")
    
    return result


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str, db: Session = Depends(get_db)):
    """Get a single template by ID."""
    # Check system templates first
    for tpl in get_all_system_templates():
        if tpl.id == template_id:
            return TemplateResponse(
                id=tpl.id, name=tpl.name, display_name=tpl.display_name,
                description=tpl.description, category=tpl.category,
                icon=tpl.icon, color=tpl.color,
                sections=[TemplateSectionDTO(
                    title=s.title, instruction=s.instruction,
                    output_key=s.output_key, output_type=s.output_type,
                ) for s in tpl.sections],
                tags=tpl.tags, is_system=True, is_active=tpl.is_active,
            )
    
    # Check DB
    try:
        dt = db.query(models.SummaryTemplateModel).filter_by(id=template_id).first()
        if dt:
            return TemplateResponse(
                id=str(dt.id), name=dt.name, display_name=dt.display_name,
                description=dt.description or "", category=dt.category or "custom",
                icon=dt.icon or "FileText", color=dt.color or "brand-cta",
                sections=[TemplateSectionDTO(**s) for s in (dt.sections or [])],
                tags=dt.tags or [], is_system=False, is_active=dt.is_active,
            )
    except Exception:
        pass
    
    raise HTTPException(status_code=404, detail="Template not found")


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(req: CreateTemplateRequest, db: Session = Depends(get_db)):
    """Create a new user template (or fork from a system template)."""
    import uuid
    
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
    
    new_id = str(uuid.uuid4())
    dt = models.SummaryTemplateModel(
        id=new_id,
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        category=req.category,
        icon=req.icon,
        color=req.color,
        sections=sections_data,
        tags=req.tags,
        is_system=False,
        is_active=True,
    )
    db.add(dt)
    db.commit()
    db.refresh(dt)
    
    return TemplateResponse(
        id=str(dt.id), name=dt.name, display_name=dt.display_name,
        description=dt.description or "", category=dt.category or "custom",
        icon=dt.icon or "FileText", color=dt.color or "brand-cta",
        sections=[TemplateSectionDTO(**s) for s in (dt.sections or [])],
        tags=dt.tags or [], is_system=False, is_active=dt.is_active,
    )


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: str, req: UpdateTemplateRequest, db: Session = Depends(get_db)):
    """Update a user-created template."""
    dt = db.query(models.SummaryTemplateModel).filter_by(id=template_id).first()
    if not dt:
        raise HTTPException(status_code=404, detail="Template not found")
    if dt.is_system:
        raise HTTPException(status_code=403, detail="Cannot modify system templates")
    
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
    
    return TemplateResponse(
        id=str(dt.id), name=dt.name, display_name=dt.display_name,
        description=dt.description or "", category=dt.category or "custom",
        icon=dt.icon or "FileText", color=dt.color or "brand-cta",
        sections=[TemplateSectionDTO(**s) for s in (dt.sections or [])],
        tags=dt.tags or [], is_system=False, is_active=dt.is_active,
    )


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str, db: Session = Depends(get_db)):
    """Delete a user-created template."""
    dt = db.query(models.SummaryTemplateModel).filter_by(id=template_id).first()
    if not dt:
        raise HTTPException(status_code=404, detail="Template not found")
    if dt.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system templates")
    
    db.delete(dt)
    db.commit()
