"""GPU worker error hierarchy tests."""

import sys

sys.path.insert(0, "gpu-worker")

from core.errors import AudioError, ModelError, PipelineError, TranscriptionTimeoutError


def test_audio_error_is_pipeline_error():
    err = AudioError("ffmpeg failed")
    assert isinstance(err, PipelineError)


def test_timeout_error_is_pipeline_error():
    err = TranscriptionTimeoutError("timed out")
    assert isinstance(err, PipelineError)


def test_model_error_is_pipeline_error():
    err = ModelError("model crash")
    assert isinstance(err, PipelineError)
