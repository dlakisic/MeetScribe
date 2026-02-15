"""
GPU Worker - Transcription service (Facade)
This file is kept for backward compatibility and CLI usage.
It delegates logic to `core/` modules.
"""

from pathlib import Path

from core.pipeline import MeetingPipeline
from core.transcriber import WhisperTranscriber


# Backward compatibility class
class Transcriber(WhisperTranscriber):
    """Facade for WhisperTranscriber to maintain compatibility."""

    pass


def process_meeting(
    mic_path: Path,
    tab_path: Path,
    metadata: dict,
    output_path: Path,
    model_size: str = "large-v3",
    device: str = "cuda",
) -> dict:
    """Facade for processing a meeting."""
    pipeline = MeetingPipeline(model_size=model_size, device=device)
    return pipeline.process(
        mic_path=mic_path,
        tab_path=tab_path,
        metadata=metadata,
        output_path=output_path,
    )


def main():
    """CLI entry point."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Transcribe meeting recordings")
    parser.add_argument("--mic", required=True, help="Path to microphone audio file")
    parser.add_argument("--tab", required=True, help="Path to tab audio file")
    parser.add_argument("--metadata", required=True, help="Path to metadata JSON file")
    parser.add_argument("--output", required=True, help="Path to output JSON file")
    parser.add_argument("--model", default="large-v3", help="Whisper model size")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="Device to use")

    args = parser.parse_args()

    with open(args.metadata, encoding="utf-8") as f:
        metadata = json.load(f)

    result = process_meeting(
        mic_path=Path(args.mic),
        tab_path=Path(args.tab),
        metadata=metadata,
        output_path=Path(args.output),
        model_size=args.model,
        device=args.device,
    )

    print("\n" + "=" * 60)
    print("TRANSCRIPT")
    print("=" * 60)
    print(result.get("formatted", ""))


if __name__ == "__main__":
    main()
