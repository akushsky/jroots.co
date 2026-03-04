from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.middleware.logging import LoggingMiddleware
from app.routers import admin, auth, images, search, telegram
from app.utils.logging_config import setup_logging

settings = get_settings()
setup_logging(loki_hostname=settings.loki_hostname, environment=settings.environment)


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

app.include_router(search.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(images.router)
app.include_router(telegram.router)


@app.get("/api/health")
async def health_check():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "healthy"}
