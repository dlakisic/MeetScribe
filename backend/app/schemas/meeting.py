from pydantic import BaseModel


class SegmentUpdate(BaseModel):
    text: str


class MeetingUpdate(BaseModel):
    title: str | None = None


class SpeakerUpdate(BaseModel):
    old_name: str
    new_name: str
