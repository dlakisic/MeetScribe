import json
from pathlib import Path

from .domain import TranscriptSegment
from .transcriber import WhisperTranscriber


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
    def __init__(self, model_size: str = "large-v3", device: str = "cuda"):
        self.transcriber = WhisperTranscriber(model_size, device)
        self.model_size = model_size
        self.device = device

    def process(
        self,
        mic_path: Path,
        tab_path: Path,
        metadata: dict,
        output_path: Path,
    ) -> dict:
        local_speaker = metadata.get("local_speaker", "Dino")
        remote_speaker = metadata.get("remote_speaker", "Interlocuteur")

        print(f"Transcribing microphone track as '{local_speaker}'...")
        mic_segments = self.transcriber.transcribe_file(mic_path, local_speaker)

        print(f"Transcribing tab audio track as '{remote_speaker}'...")
        tab_segments = self.transcriber.transcribe_file(tab_path, remote_speaker)

        mic_offset = metadata.get("mic_start_offset", 0.0)
        tab_offset = metadata.get("tab_start_offset", 0.0)

        merged = merge_transcripts(
            mic_segments,
            tab_segments,
            mic_offset=mic_offset,
            tab_offset=tab_offset,
        )
        print(f"Merged transcript: {len(merged)} total segments")

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

        print(f"Transcript saved to {output_path}")
        return result
