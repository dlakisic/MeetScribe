from dataclasses import dataclass

@dataclass
class TranscriptSegment:
    speaker: str
    text: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start": self.start,
            "end": self.end,
        }
