"""Classified errors for the GPU worker pipeline."""


class PipelineError(Exception):
    """Base class for pipeline errors."""


class AudioError(PipelineError):
    """Error during audio conversion (ffmpeg)."""


class TranscriptionTimeoutError(PipelineError):
    """Operation exceeded its time limit."""


class ModelError(PipelineError):
    """Error during model inference (Whisper or pyannote)."""
