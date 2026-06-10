"""
Routes package initialization
"""

from fastapi import APIRouter
from app.routes.search_org import router as search_org_router
from app.routes.meeting_ops import router as meeting_ops_router
from app.routes.cloud_tasks import router as cloud_tasks_router
from app.routes.callbacks import router as callbacks_router
from app.routes.templates import router as templates_router
from app.routes.rag import router as rag_router
from app.routes.websocket import router as websocket_router
from app.routes.meetings import router as meetings_router
from app.routes.intent import router as intent_router
from app.routes.feedback import router as feedback_router
from app.routes.admin import router as admin_router
from app.routes.glossary import router as glossary_router
from app.routes.ops_admin import router as ops_admin_router

# Main router that includes all sub-routers
api_router = APIRouter()
api_router.include_router(search_org_router)
api_router.include_router(meeting_ops_router)
api_router.include_router(cloud_tasks_router)
api_router.include_router(callbacks_router)
api_router.include_router(templates_router)
api_router.include_router(rag_router)
api_router.include_router(websocket_router)
api_router.include_router(meetings_router)
api_router.include_router(intent_router)
api_router.include_router(feedback_router)
api_router.include_router(admin_router)
api_router.include_router(glossary_router)
api_router.include_router(ops_admin_router)

