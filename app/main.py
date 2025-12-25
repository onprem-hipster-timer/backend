from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db.session import init_db
from app.api.schedule import router as schedule_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup logic
    init_db()
    yield
app = FastAPI(
    title="onperm-hipster-timer-backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(schedule_router)
