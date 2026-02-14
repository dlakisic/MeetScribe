from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    """An action item extracted from the meeting transcript."""

    description: str = Field(..., description="The task description")
    owner: str | None = Field(None, description="The person responsible for the task")
    deadline: str | None = Field(
        None, description="The deadline for the task, if mentioned (ISO format or relative)"
    )
    status: str = Field("open", description="Initial status of the task")


class KeyDecision(BaseModel):
    """A key decision made during the meeting."""

    decision: str = Field(..., description="The decision made")
    context: str | None = Field(None, description="Context or reason for the decision")


class MeetingSummary(BaseModel):
    """Structured summary of the meeting."""

    abstract: str = Field(..., description="A concise executive summary (3-5 sentences)")
    topics: list[str] = Field(..., description="List of main topics discussed")
    sentiment: str = Field(
        ...,
        description="Overall sentiment of the meeting (positive, neutral, negative, tense, productive)",
    )


class BusinessInsights(BaseModel):
    """Business intelligence extracted from the meeting."""

    objections: list[str] = Field(
        default_factory=list, description="Client objections or concerns raised"
    )
    negotiation_points: list[str] = Field(
        default_factory=list, description="Points of negotiation (price, terms, scope)"
    )
    competitors_mentioned: list[str] = Field(
        default_factory=list, description="Competitors mentioned by the client"
    )
    budget_range: str | None = Field(None, description="Budget constraints or range discussed")


class ExtractedData(BaseModel):
    """Container for all extracted data."""

    summary: MeetingSummary
    action_items: list[ActionItem] = Field(default_factory=list)
    decisions: list[KeyDecision] = Field(default_factory=list)
    business_insights: BusinessInsights = Field(default_factory=BusinessInsights)
