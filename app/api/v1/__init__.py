from fastapi import APIRouter
from app.api.v1.schedules import router as schedules_router

api_router = APIRouter()

api_router.include_router(schedules_router, prefix="/v1")
