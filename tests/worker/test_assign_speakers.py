"""Speaker assignment from diarization turns."""

import sys

sys.path.insert(0, "gpu-worker")

from core.diarizer import assign_speakers
from core.domain import TranscriptSegment


def _seg(start, end):
    return TranscriptSegment(speaker="Interlocuteur", text="...", start=start, end=end)


def test_segment_takes_speaker_with_most_overlap():
    segments = [_seg(0.0, 4.0)]
    assign_speakers(segments, [(0.0, 1.0, "SPEAKER_00"), (1.0, 4.0, "SPEAKER_01")])
    assert segments[0].speaker == "Speaker 2"


def test_segment_without_overlap_takes_closest_turn():
    segments = [_seg(10.0, 11.0)]
    turns = [(0.0, 5.0, "SPEAKER_00"), (11.5, 20.0, "SPEAKER_01")]
    assign_speakers(segments, turns)
    assert segments[0].speaker == "Speaker 2"


def test_no_turns_keeps_default_labels():
    segments = [_seg(0.0, 1.0)]
    assign_speakers(segments, [])
    assert segments[0].speaker == "Interlocuteur"
