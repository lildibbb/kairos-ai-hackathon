from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Intent = Literal["slow_internet", "no_internet", "disconnecting", "voice", "iptv", "other"]


class CustomerChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=1000, examples=["My internet is slow, I want to make a report."])
    conversation_id: UUID | None = None
    request_id: UUID = Field(default_factory=uuid4)
    answer_choice: str | None = Field(default=None, max_length=40)
    action_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action_confirmation(self):
        confirming = self.answer_choice in ("confirm_router_action", "cancel_router_action")
        if confirming != (self.action_id is not None):
            raise ValueError("An action ID is required only for a confirmation or cancellation")
        return self


class ReportedSymptoms(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent = "other"
    connection: Literal["wifi", "wired", "unknown"] = "unknown"
    device_scope: Literal["one", "all", "unknown"] = "unknown"
    near_router: Literal["better", "same", "unknown"] = "unknown"


TroubleshootingCheck = Literal["another_device", "ethernet", "near_router", "pause_downloads", "check_cables", "restart_router", "tv_inputs"]


class CustomerSymptomInterpretation(ReportedSymptoms):
    check_outcome: Literal["unknown", "failed", "resolved"] = "unknown"
    checks_tried: list[TroubleshootingCheck] = Field(default_factory=list, max_length=7)


class DiagnosticFinding(BaseModel):
    code: str
    observation: str
    interpretation: str
    evidence_status: Literal["current", "simulated", "stale", "invalid", "unverified", "stored_configuration"]
    observed_at: datetime | None = None


class AnswerChoice(BaseModel):
    value: str
    label: str


class FollowUpQuestion(BaseModel):
    id: str
    question: str
    choices: list[AnswerChoice] = Field(default_factory=list)


class CustomerKnowledgeSource(BaseModel):
    chunk_id: str
    title: str
    section: str


class ChatWorkflow(BaseModel):
    report_requested: bool = False
    router_lights: Literal["red_los", "no_red_los", "unknown"] = "unknown"
    self_help: Literal["untried", "resolved", "failed"] = "untried"
    escalation_reason: str | None = None
    traffic_pause: Literal["untried", "better", "same"] = "untried"
    requested_action: Literal["none", "mesh", "plans", "store", "technician", "troubleshoot", "reboot", "vlan"] = "none"
    requested_service: Literal["HSI", "IPTV", "VoBB"] = "HSI"
    checks_tried: list[TroubleshootingCheck] = Field(default_factory=list)


class CustomerCase(BaseModel):
    category: Literal["unknown", "coverage", "bandwidth_capacity", "radio_congestion", "profile_review", "fibre_fault"] = "unknown"
    evidence: list[str] = Field(default_factory=list)
    sales_categories: list[Literal["mesh", "plan"]] = Field(default_factory=list)
    capacity_check_suggested: bool = False


class CustomerSalesOption(BaseModel):
    id: str
    name: str
    description: str
    official_url: str
    monthly_price_myr: float | None = None
    contract_months: int | None = None
    eligibility_note: str


class CustomerReportReceipt(BaseModel):
    ticket_id: str | None = None
    reference: str
    status: Literal["assigned", "queued"]
    is_demo: bool


ChatStatus = Literal["possible_issue", "needs_live_check", "needs_more_information", "self_help", "resolved", "report_created", "sales_options", "action_confirmation", "action_completed", "action_cancelled"]


class CustomerRouterActionRead(BaseModel):
    id: str
    kind: Literal["reboot", "restore_vlan"]
    label: str
    status: Literal["pending", "succeeded", "cancelled", "expired"]
    simulation: Literal[True] = True
    expires_at: datetime


class CustomerAgentStep(BaseModel):
    tool: str
    outcome: Literal["observed", "selected", "fallback"]


class CustomerChatResponse(BaseModel):
    conversation_id: str
    request_id: str
    checked_at: datetime
    answer: str
    status: ChatStatus
    reported: ReportedSymptoms
    findings: list[DiagnosticFinding]
    follow_up: FollowUpQuestion | None
    warnings: list[str]
    knowledge_sources: list[CustomerKnowledgeSource]
    knowledge_status: Literal["available", "unavailable", "none"]
    mode: Literal["local", "hosted", "fallback"]
    no_actions_taken: bool = True
    workflow: ChatWorkflow = Field(default_factory=ChatWorkflow)
    assessment: CustomerCase = Field(default_factory=CustomerCase)
    sales_options: list[CustomerSalesOption] = Field(default_factory=list)
    report: CustomerReportReceipt | None = None
    is_demo: bool = True
    orchestration: Literal["guided", "agent_hosted", "agent_local", "agent_fallback"] = "guided"
    agent_trace: list[CustomerAgentStep] = Field(default_factory=list)
    router_action: CustomerRouterActionRead | None = None
    router_action_details: dict | None = None
    submitted_action_id: str | None = None
    response_mode: Literal["static", "hosted", "fallback"] = "static"
    response_prefix: str | None = None


class CustomerVisibleReportReceipt(BaseModel):
    ticket_id: str | None = None
    reference: str
    status: Literal["assigned", "queued"]


class CustomerVisibleResponse(BaseModel):
    """Only customer-facing outcomes; internal evidence stays server-side."""
    conversation_id: str
    request_id: str
    checked_at: datetime
    answer: str
    status: ChatStatus
    follow_up: FollowUpQuestion | None
    report: CustomerVisibleReportReceipt | None = None
    sales_options: list[CustomerSalesOption] = Field(default_factory=list)
    router_action: CustomerRouterActionRead | None = None


class CustomerVisibleTurn(BaseModel):
    message: str
    response: CustomerVisibleResponse


class CustomerVisibleHistory(BaseModel):
    conversation_id: str
    turns: list[CustomerVisibleTurn]


class CustomerChatHistoryTurn(BaseModel):
    message: str
    response: CustomerChatResponse


class CustomerChatHistory(BaseModel):
    conversation_id: str
    turns: list[CustomerChatHistoryTurn]
