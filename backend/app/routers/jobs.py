from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_job_store, require_auth
from ..services.job_store import JobStore

router = APIRouter(prefix="/api/status", dependencies=[Depends(require_auth)])


@router.get("")
async def list_active_jobs(job_store: JobStore = Depends(get_job_store)):
    """Jobs still queued or processing, so clients can resume progress display."""
    return {"jobs": await job_store.list_active()}


@router.get("/{job_id}")
async def get_job_status(job_id: str, job_store: JobStore = Depends(get_job_store)):
    """Get the status of a transcription job."""
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
