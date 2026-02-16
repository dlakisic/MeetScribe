import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

from .audio import convert_to_wav
from .domain import TranscriptSegment


class WhisperTranscriber:
    def __init__(
        self, model_size: str = "large-v3", device: str = "cuda", language: str | None = None
    ):
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type="float16" if device == "cuda" else "int8",
        )
        self.device = device
        self.language = language  # None = auto-detect

    def transcribe_file(
        self, audio_path: Path, speaker_label: str, ffmpeg_timeout: int = 300
    ) -> list[TranscriptSegment]:
        if audio_path.suffix.lower() != ".wav":
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = Path(tmp.name)
            convert_to_wav(audio_path, wav_path, timeout=ffmpeg_timeout)
        else:
            wav_path = audio_path

        try:
            segments, info = self.model.transcribe(
                str(wav_path),
                language=self.language,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )

            result = []
            for segment in segments:
                result.append(
                    TranscriptSegment(
                        speaker=speaker_label,
                        text=segment.text.strip(),
                        start=segment.start,
                        end=segment.end,
                    )
                )
            return result

        finally:
            if wav_path != audio_path and wav_path.exists():
                wav_path.unlink()
