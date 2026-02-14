"""
GPU Worker HTTP Server
Receives audio files via HTTP and returns transcripts
"""

import asyncio
import json
import tempfile
from pathlib import Path

import uvicorn
from core.logging import get_logger
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from transcribe import Transcriber, process_meeting

log = get_logger("server")

app = FastAPI(title="MeetScribe GPU Worker", version="0.1.0")

# Global transcriber instance (loaded once)
_transcriber: Transcriber | None = None
_model_size: str = "large-v3"
_device: str = "cuda"
_lock: asyncio.Lock | None = None


def get_transcriber() -> Transcriber:
    """Get or create the transcriber instance."""
    global _transcriber
    if _transcriber is None:
        log.info(f"Loading Whisper model '{_model_size}' on {_device}")
        _transcriber = Transcriber(model_size=_model_size, device=_device)
        log.info("Model loaded")
    return _transcriber


@app.on_event("startup")
async def startup():
    """Preload model on startup and initialize lock."""
    global _lock
    _lock = asyncio.Lock()

    # Run in thread to not block
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_transcriber)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": _model_size,
        "device": _device,
        "model_loaded": _transcriber is not None,
        "locked": _lock.locked() if _lock else False,
    }


@app.post("/transcribe")
async def transcribe(
    mic_file: UploadFile = File(..., description="Microphone audio file"),
    tab_file: UploadFile = File(..., description="Tab audio file"),
    metadata: str = Form(..., description="Meeting metadata as JSON"),
):
    """Transcribe uploaded audio files.

    Accepts two audio files (mic and tab) plus metadata JSON.
    Returns the complete transcript.
    """
    if not _lock:
        raise HTTPException(status_code=500, detail="Server not initialized")

    if _lock.locked():
        log.info("Worker is busy, queueing request")

    async with _lock:
        log.info("Acquired lock, starting transcription")
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid metadata JSON")

        # Create temp directory for this job
        job_dir = Path(tempfile.mkdtemp())

        try:
            # Save uploaded files
            mic_path = job_dir / f"mic_{mic_file.filename}"
            tab_path = job_dir / f"tab_{tab_file.filename}"
            output_path = job_dir / "output.json"

            with open(mic_path, "wb") as f:
                content = await mic_file.read()
                f.write(content)

            with open(tab_path, "wb") as f:
                content = await tab_file.read()
                f.write(content)

            # Run transcription in threadpool to avoid blocking event loop
            # process_meeting is blocking (CPU/GPU bound)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: process_meeting(
                    mic_path=mic_path,
                    tab_path=tab_path,
                    metadata=meta,
                    output_path=output_path,
                    model_size=_model_size,
                    device=_device,
                ),
            )

            return JSONResponse(content=result)

        except Exception as e:
            log.error(f"Transcription failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            # Cleanup temp files
            import shutil

            shutil.rmtree(job_dir, ignore_errors=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GPU Worker HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--model", default="large-v3", help="Whisper model size")
    parser.add_argument("--device", default="cuda", help="Device (cuda/cpu)")

    args = parser.parse_args()

    global _model_size, _device
    _model_size = args.model
    _device = args.device

    log.info(f"Starting GPU Worker on {args.host}:{args.port}")
    log.info(f"Model: {_model_size}, Device: {_device}")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
