from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import load_config
from .core.logging import get_logger
from .database import Database
from .gpu_client import TranscriptionService
from .repositories.meeting_repository import MeetingRepository
from .routers import jobs, meetings, segments, transcripts, upload
from .services.extraction_service import ExtractionService
from .services.job_store import JobStore
from .services.meeting_service import MeetingService

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - setup and teardown."""
    # Load config and attach to app state
    config = load_config()
    app.state.config = config

    # Initialize DB
    db = Database(config.db_path)
    await db.connect()
    app.state.db = db

    # Initialize infrastructure and services
    repo = MeetingRepository(db)
    transcriber = TranscriptionService(config)
    job_store = JobStore()
    extraction_service = ExtractionService()

    meeting_service = MeetingService(repo, transcriber, job_store, extraction_service)

    # Attach services to app state for dependencies
    app.state.meeting_service = meeting_service
    app.state.job_store = job_store

    log.info("Backend started")
    log.info(f"Data dir: {config.data_dir}")
    log.info(f"GPU worker: {config.gpu.ssh_user}@{config.gpu.host}")
    log.info(f"Fallback enabled: {config.fallback.enabled}")

    yield

    await db.close()


app = FastAPI(
    title="MeetScribe API",
    description="Self-hosted meeting transcription backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router)
app.include_router(meetings.router)
app.include_router(transcripts.router)
app.include_router(segments.router)
app.include_router(jobs.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "MeetScribe", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    # Access services via app.state in simple checks, or use dependency injection in routes
    # Here we are in a simple route, we can access app.state if we had request
    # But strictly speaking, we are inside a route handler.
    # Let's keep it simple and just return static status for now,
    # or rely on dependencies if we move this to a router properly.
    # For now, let's access via global app if needed or just return basic info.

    # Ideally health check should check DB and GPU.
    # We can use the app reference from global scope since we are in main.py

    gpu_available = False
    fallback = False

    if hasattr(app.state, "meeting_service"):
        gpu_available = await app.state.meeting_service.transcriber.gpu_client.is_gpu_available()

    if hasattr(app.state, "config"):
        fallback = app.state.config.fallback.enabled

    return {
        "status": "ok",
        "gpu_available": gpu_available,
        "fallback_enabled": fallback,
    }


# Simple CLI to run the server
def main():
    import uvicorn

    config = load_config()
    uvicorn.run(
        "backend.app.main:app",
        host=config.host,
        port=config.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
