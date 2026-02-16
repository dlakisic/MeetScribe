import subprocess
from pathlib import Path

from .errors import AudioError, TranscriptionTimeoutError


def convert_to_wav(input_path: Path, output_path: Path, timeout: int = 300) -> None:
    """Convert audio file to WAV 16kHz mono using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise TranscriptionTimeoutError(f"ffmpeg conversion timed out (>{timeout}s)")
    if result.returncode != 0:
        raise AudioError(f"ffmpeg conversion failed: {result.stderr}")
