from pydantic import BaseModel, Field


class AssistantMessageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AssistantCitationRead(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    section: str
    source_type: str
    content: str
    score: float


class NextBestActionRead(BaseModel):
    remediation: str | None = None
    dispatch_required: bool = False
    suggestion: str | None = None
    evidence: list[str] = Field(default_factory=list)
    suggestion_evidence: list[str] = Field(default_factory=list)


class AssistantSummaryRead(BaseModel):
    problem: str
    solution: str | None = None
    product_recommendation: str | None = None
    actions: list[str] = Field(default_factory=list)


class AssistantAnswerRead(BaseModel):
    session_id: str
    answer: str
    uncertainty: str
    has_evidence: bool
    citations: list[AssistantCitationRead]
    next_best_action: NextBestActionRead | None = None
    summary: AssistantSummaryRead | None = None
    action_intent: str | None = None
