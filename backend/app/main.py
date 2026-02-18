from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Config, load_config
from .core.logging import get_logger
from .database import Database
from .dependencies import get_config, get_meeting_service
from .repositories.meeting_repository import MeetingRepository
from .routers import jobs, meetings, segments, transcripts, upload
from .services.extraction_service import ExtractionService
from .services.job_store import JobStore
from .services.meeting_service import MeetingService
from .transcription import TranscriptionService

log = get_logger("api")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to request state and response headers."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - setup and teardown."""
    config = load_config()
    app.state.config = config

    db = Database(config.db_path)
    await db.connect()
    app.state.db = db

    repo = MeetingRepository(db)
    job_store = JobStore(db)
    await job_store.cleanup_old_jobs()
    extraction_service = ExtractionService()

    from .transcription.fallback import FallbackTranscriber
    from .transcription.gpu_client import GPUClient

    gpu_client = GPUClient(config)
    fallback = FallbackTranscriber(config) if config.fallback.enabled else None
    gpu_waker = None

    if config.smart_plug.enabled:
        from .smart_plug import SmartPlug
        from .transcription.gpu_waker import GPUWaker

        smart_plug = SmartPlug(config.smart_plug)
        gpu_waker = GPUWaker(smart_plug, gpu_client, config.smart_plug.boot_wait_time)

    transcriber = TranscriptionService(gpu_client, fallback, gpu_waker)

    meeting_service = MeetingService(repo, transcriber, job_store, extraction_service)

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
app.add_middleware(RequestIDMiddleware)

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
async def health(
    request: Request,
    config: Config = Depends(get_config),
    service: MeetingService = Depends(get_meeting_service),
):
    """Health check endpoint."""
    request_id = getattr(request.state, "request_id", None)
    gpu_available = await service.is_gpu_available()
    log.info(
        "Health check served",
        extra={
            "request_id": request_id,
            "gpu_available": gpu_available,
            "fallback_enabled": config.fallback.enabled,
        },
    )
    return {
        "status": "ok",
        "gpu_available": gpu_available,
        "fallback_enabled": config.fallback.enabled,
    }


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
