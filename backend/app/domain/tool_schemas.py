from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ToolCatalogItemRead(BaseModel):
    name: str
    title: str
    description: str
    kind: str
    category: str
    risk: str
    requires_confirmation: bool
    target_device_types: list[str] | None


class ToolProposeRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=60)
    model_proposal: dict | None = None
    device_id: str = Field(min_length=1, max_length=64)
    parameters: dict = Field(default_factory=dict)


class AgentToolProposeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    device_id: str | None = Field(default=None, max_length=64)
    tool_name: str | None = Field(default=None, max_length=60)
    parameters: dict = Field(default_factory=dict)


class AgentPlanSuggestionRead(BaseModel):
    tool_name: str
    title: str
    description: str
    kind: str
    category: str
    risk: str
    requires_confirmation: bool
    device_id: str
    device_ref: str
    device_type: str
    parameters: dict
    rationale: str
    steps: list[str]
    evidence: list[str]
    confidence: float
    reasoning: dict = Field(default_factory=dict)


class AgentPlanRead(BaseModel):
    ticket_id: str
    question: str
    device_id: str
    summary: str
    suggestions: list[AgentPlanSuggestionRead]
    reasoning: list[dict] = Field(default_factory=list)
    alternatives: list[dict] = Field(default_factory=list)
    intent: str | None = None



class ToolProposalRead(BaseModel):
    id: str
    ticket_id: str
    tool_name: str
    device_id: str
    device_ref: str
    kind: str
    requires_confirmation: bool
    parameters: dict
    status: str
    summary: str
    confirmation_id: str
    created_at: datetime
    result: dict | None = None


class ToolConfirmRequest(BaseModel):
    confirmation_id: str = Field(min_length=1, max_length=120)


class ToolExecutionRead(BaseModel):
    id: str
    ticket_id: str
    tool_name: str
    device_id: str
    device_ref: str
    status: str
    message: str
    correlation_id: str
    executed_at: datetime
    result: dict | None = None


class AuditEventRead(BaseModel):
    id: str
    event_type: str
    actor_id: str | None
    actor_name: str | None
    ticket_id: str | None
    details: dict
    created_at: datetime
