from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AppointmentBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_id: UUID
    request_id: UUID


class AppointmentWindow(BaseModel):
    slot_id: str
    starts_at: datetime
    ends_at: datetime


class AppointmentRead(AppointmentWindow):
    id: str
    ticket_id: str
    status: Literal["confirmed", "cancelled"]


class AppointmentAvailability(BaseModel):
    timezone: str = "Asia/Kuala_Lumpur"
    slots: list[AppointmentWindow]
    appointment: AppointmentRead | None = None
