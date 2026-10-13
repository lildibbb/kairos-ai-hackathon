from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.assistant_schemas import AssistantCitationRead


class OrderProductRead(BaseModel):
    code: str
    name: str
    description: str
    monthly_price_myr: float | None = None
    one_time_price_myr: float | None = None
    speed_mbps: int | None = None
    tier: str | None = None
    features: list[str] = Field(default_factory=list)
    badge: str | None = None


class OrderOptionRead(BaseModel):
    action: str
    label: str
    recommended: bool
    products: list[OrderProductRead]


class TicketSummaryRead(BaseModel):
    ticket_id: str
    problem: str
    solution: str | None = None
    product_recommendation: str | None = None
    actions: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    citations: list[AssistantCitationRead] = Field(default_factory=list)
    order_options: list[OrderOptionRead] = Field(default_factory=list)
    plan_name: str | None = None
    plan_price_myr: float | None = None
    model: str | None = None
    generated_at: datetime | None = None
    cached: bool = False


class OrderCreateRequest(BaseModel):
    action: str = Field(min_length=1, max_length=20)
    product_code: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(default=None, max_length=500)


class OrderRead(BaseModel):
    id: str
    ticket_id: str
    action: str
    product_code: str
    product_name: str
    monthly_price_myr: float | None = None
    one_time_price_myr: float | None = None
    notes: str | None = None
    status: str
    email_status: str
    email_recipient: str | None = None
    email_error: str | None = None
    created_at: datetime | None = None
