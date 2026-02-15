import json
import os
from pathlib import Path

from .domain import TranscriptSegment
from .logging import get_logger
from .transcriber import WhisperTranscriber

log = get_logger("pipeline")


def merge_transcripts(
    mic_segments: list[TranscriptSegment],
    tab_segments: list[TranscriptSegment],
    mic_offset: float = 0.0,
    tab_offset: float = 0.0,
) -> list[TranscriptSegment]:
    """Merge two transcript timelines into one, sorted chronologically."""
    all_segments = []
    for seg in mic_segments:
        all_segments.append(
            TranscriptSegment(
                speaker=seg.speaker,
                text=seg.text,
                start=seg.start + mic_offset,
                end=seg.end + mic_offset,
            )
        )
    for seg in tab_segments:
        all_segments.append(
            TranscriptSegment(
                speaker=seg.speaker,
                text=seg.text,
                start=seg.start + tab_offset,
                end=seg.end + tab_offset,
            )
        )

    all_segments.sort(key=lambda s: s.start)
    return all_segments


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_transcript(segments: list[TranscriptSegment]) -> str:
    lines = []
    for seg in segments:
        timestamp = format_timestamp(seg.start)
        lines.append(f"[{timestamp}] {seg.speaker}: {seg.text}")
    return "\n".join(lines)


class MeetingPipeline:
    def __init__(self, model_size: str = "large-v3", device: str = "cuda", language: str | None = None):
        self.transcriber = WhisperTranscriber(model_size, device, language=language)
        self.model_size = model_size
        self.device = device
        self._diarizer = None

    def _get_diarizer(self):
        """Lazy-load the speaker diarizer (only when needed)."""
        if self._diarizer is None:
            from .diarizer import SpeakerDiarizer

            self._diarizer = SpeakerDiarizer(device=self.device)
        return self._diarizer

    def _diarize_segments(self, audio_path: Path, segments: list[TranscriptSegment]) -> None:
        """Run speaker diarization on segments if HF_TOKEN is available."""
        if not os.environ.get("HF_TOKEN"):
            log.info("HF_TOKEN not set, skipping speaker diarization")
            return

        if not segments:
            return

        try:
            from .diarizer import assign_speakers

            diarizer = self._get_diarizer()
            turns = diarizer.diarize(audio_path)
            assign_speakers(segments, turns)
            speakers = set(s.speaker for s in segments)
            log.info(f"Diarization applied: {len(speakers)} speakers identified")
        except Exception as e:
            log.warning(f"Diarization failed, keeping default labels: {e}")

    def process(
        self,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
        output_path: Path,
    ) -> dict:
        local_speaker = metadata.get("local_speaker", "Dino")
        remote_speaker = metadata.get("remote_speaker", "Interlocuteur")

        has_mic = mic_path and mic_path.exists()
        has_tab = tab_path and tab_path.exists()

        # Transcribe mic track (always tagged as local speaker)
        mic_segments = []
        if has_mic:
            log.info(f"Transcribing microphone track as '{local_speaker}'")
            mic_segments = self.transcriber.transcribe_file(mic_path, local_speaker)

        # Transcribe tab track
        tab_segments = []
        if has_tab:
            log.info(f"Transcribing tab audio track as '{remote_speaker}'")
            tab_segments = self.transcriber.transcribe_file(tab_path, remote_speaker)

        # Speaker diarization
        if has_tab:
            # Tab always gets diarization (multiple remote speakers possible)
            self._diarize_segments(tab_path, tab_segments)
        elif has_mic and not has_tab:
            # Mic-only: diarize to distinguish speakers
            self._diarize_segments(mic_path, mic_segments)

        mic_offset = metadata.get("mic_start_offset", 0.0)
        tab_offset = metadata.get("tab_start_offset", 0.0)

        merged = merge_transcripts(
            mic_segments,
            tab_segments,
            mic_offset=mic_offset,
            tab_offset=tab_offset,
        )
        log.info(f"Merged transcript: {len(merged)} segments")

        result = {
            "meeting": {
                "title": metadata.get("title", "Untitled Meeting"),
                "date": metadata.get("date"),
                "duration": metadata.get("duration"),
                "platform": metadata.get("platform"),
                "url": metadata.get("url"),
            },
            "segments": [seg.to_dict() for seg in merged],
            "formatted": format_transcript(merged),
            "stats": {
                "total_segments": len(merged),
                "mic_segments": len(mic_segments),
                "tab_segments": len(tab_segments),
                "device": self.device,
                "model": self.model_size,
            },
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        log.info(f"Transcript saved to {output_path}")
        return result
