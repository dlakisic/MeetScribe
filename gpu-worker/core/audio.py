import subprocess
from pathlib import Path

import numpy as np

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


def load_waveform(input_path: Path, sample_rate: int = 16000, timeout: int = 300) -> np.ndarray:
    """Decode any audio file to a mono float32 waveform with ffmpeg."""
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        "-f",
        "f32le",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise TranscriptionTimeoutError(f"ffmpeg decoding timed out (>{timeout}s)")
    if result.returncode != 0:
        raise AudioError(f"ffmpeg decoding failed: {result.stderr.decode(errors='replace')}")
    return np.frombuffer(result.stdout, dtype=np.float32)
