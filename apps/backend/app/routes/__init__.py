"""
Routes package initialization
"""

from fastapi import APIRouter
from app.routes.search_org import router as search_org_router
from app.routes.meeting_ops import router as meeting_ops_router
from app.routes.cloud_tasks import router as cloud_tasks_router

# Main router that includes all sub-routers
api_router = APIRouter()
api_router.include_router(search_org_router)
api_router.include_router(meeting_ops_router)
api_router.include_router(cloud_tasks_router)

