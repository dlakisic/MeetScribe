"""Speaker diarization using pyannote-audio."""

import concurrent.futures
import os
from pathlib import Path

from .audio import load_waveform
from .domain import TranscriptSegment
from .errors import ModelError, TranscriptionTimeoutError
from .logging import get_logger

log = get_logger("diarizer")

DEFAULT_PIPELINE = "pyannote/speaker-diarization-community-1"
SAMPLE_RATE = 16000


class SpeakerDiarizer:
    """Identifies who speaks when using pyannote speaker-diarization."""

    def __init__(self, device: str = "cuda"):
        import torch
        from pyannote.audio import Pipeline

        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError(
                "HF_TOKEN environment variable required for speaker diarization. "
                "Get a token at https://huggingface.co/settings/tokens and accept "
                "the conditions of the pyannote pipeline on its Hugging Face page"
            )

        model = os.environ.get("PYANNOTE_PIPELINE") or DEFAULT_PIPELINE
        log.info(f"Loading pyannote pipeline {model}")
        # pyannote.audio 4 renamed use_auth_token to token.
        self.pipeline = Pipeline.from_pretrained(model, token=hf_token)
        if self.pipeline is None:
            raise RuntimeError(
                f"Could not load {model}: accept its conditions at https://huggingface.co/{model}"
            )
        self.pipeline.to(torch.device(device))
        log.info("Diarization pipeline loaded")

    def diarize(self, audio_path: Path, timeout: int = 600) -> list[tuple[float, float, str]]:
        """Run diarization on an audio file with timeout guard.

        Returns a list of (start, end, speaker_label) turns.
        Note: ThreadPoolExecutor timeout doesn't kill the thread — the pipeline
        continues in background but will complete naturally or on process restart.
        """
        log.info(f"Running diarization on {audio_path.name} (timeout={timeout}s)")

        import torch

        # Decode with ffmpeg and pass the waveform: pyannote's own file reading is
        # not sample-accurate on compressed formats (MP3 chunks come back short).
        waveform = load_waveform(audio_path, SAMPLE_RATE)
        audio = {
            "waveform": torch.from_numpy(waveform.copy()).unsqueeze(0),
            "sample_rate": SAMPLE_RATE,
        }

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.pipeline, audio)
        try:
            diarization = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            executor.shutdown(wait=False)
            raise TranscriptionTimeoutError(
                f"Diarization timed out (>{timeout}s) on {audio_path.name}"
            )
        except Exception as e:
            executor.shutdown(wait=False)
            raise ModelError(f"Diarization model error: {e}")
        else:
            executor.shutdown(wait=False)

        # pyannote.audio 4 returns a DiarizeOutput; its exclusive variant has no
        # overlapping turns, which suits aligning with transcript segments.
        # Legacy pipelines return the Annotation directly.
        annotation = getattr(diarization, "exclusive_speaker_diarization", diarization)

        turns = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            turns.append((turn.start, turn.end, speaker))

        speakers = set(t[2] for t in turns)
        log.info(f"Diarization complete: {len(turns)} turns, {len(speakers)} speakers")
        return turns


def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[tuple[float, float, str]],
) -> list[TranscriptSegment]:
    """Assign speaker labels from diarization turns to transcript segments.

    Uses majority-overlap: each segment gets the speaker of the
    diarization turn that overlaps it the most.
    """
    if not turns:
        return segments

    for seg in segments:
        best_speaker = seg.speaker  # Keep existing if no overlap
        best_overlap = 0.0
        for turn_start, turn_end, speaker in turns:
            overlap = min(seg.end, turn_end) - max(seg.start, turn_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        seg.speaker = _friendly_label(best_speaker)

    return segments


def _friendly_label(pyannote_label: str) -> str:
    """Convert 'SPEAKER_00' to 'Speaker 1'."""
    try:
        num = int(pyannote_label.split("_")[-1])
        return f"Speaker {num + 1}"
    except ValueError:
        return pyannote_label
