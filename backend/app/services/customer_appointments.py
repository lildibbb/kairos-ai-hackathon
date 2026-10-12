"""Customer-scoped, atomic reservations against a shared physical technician calendar."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.policy import require_role
from app.domain.appointment_schemas import AppointmentAvailability, AppointmentRead, AppointmentWindow
from app.domain.models import (AppointmentSlot, AuditEvent, Customer, CustomerAccount, CustomerAppointment,
    CustomerDispatchArea, CustomerTroubleTicket, DispatchArea, Role, TechnicianDispatchArea, TechnicianShift, User)


class AppointmentNotFoundError(Exception):
    pass


class AppointmentConflictError(Exception):
    pass


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def owned_ticket(session, actor, ticket_id, *, lock=False):
    require_role(actor.role, ("customer",))
    link = session.get(CustomerAccount, actor.id)
    if link is None:
        raise AppointmentNotFoundError()
    if lock:
        session.scalar(select(Customer).where(Customer.id == link.customer_id).with_for_update())
    statement = select(CustomerTroubleTicket).where(CustomerTroubleTicket.id == str(ticket_id), CustomerTroubleTicket.customer_id == link.customer_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    ticket = session.scalar(statement)
    if ticket is None:
        raise AppointmentNotFoundError()
    return ticket


def active_appointment(session, ticket_id):
    return session.scalar(select(CustomerAppointment).where(CustomerAppointment.ticket_id == ticket_id, CustomerAppointment.status == "confirmed"))


def appointment_read(session, appointment):
    slot = session.get(AppointmentSlot, appointment.slot_id)
    return AppointmentRead(id=appointment.id, ticket_id=appointment.ticket_id, status=appointment.status,
        slot_id=slot.id, starts_at=utc(slot.starts_at), ends_at=utc(slot.ends_at))


def _eligible_technicians(session, ticket):
    mapping = session.get(CustomerDispatchArea, ticket.customer_id)
    area = session.get(DispatchArea, ticket.area_id) if ticket.area_id else None
    if not mapping or not area or mapping.area_id != area.id or not area.is_active or area.is_demo != ticket.is_demo:
        return []
    return list(session.scalars(select(User.id).join(Role).join(TechnicianDispatchArea, TechnicianDispatchArea.user_id == User.id).where(
        Role.name == "technician", User.is_active.is_(True), User.is_demo == ticket.is_demo,
        TechnicianDispatchArea.area_id == area.id, TechnicianDispatchArea.is_available.is_(True))))


def _fits_shift(session, slot, *, lock=False):
    statement = select(TechnicianShift).where(TechnicianShift.technician_id == slot.technician_id).order_by(TechnicianShift.id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    shifts = list(session.scalars(statement))
    start, end = utc(slot.starts_at), utc(slot.reserved_until)
    working = any(row.kind == "working" and utc(row.starts_at) <= start and end <= utc(row.ends_at) for row in shifts)
    unavailable = any(row.kind == "unavailable" and utc(row.starts_at) < end and start < utc(row.ends_at) for row in shifts)
    return working and not unavailable


def availability(session, actor, ticket_id, *, now=None):
    now = utc(now or datetime.now(UTC))
    ticket = owned_ticket(session, actor, ticket_id)
    active = active_appointment(session, ticket.id)
    slots = []
    if ticket.status in ("assigned", "queued"):
        eligible = _eligible_technicians(session, ticket)
        occupied = select(CustomerAppointment.slot_id).where(CustomerAppointment.status == "confirmed")
        candidates = session.scalars(select(AppointmentSlot).where(AppointmentSlot.technician_id.in_(eligible), AppointmentSlot.is_active.is_(True),
            AppointmentSlot.starts_at >= now + timedelta(hours=2), AppointmentSlot.starts_at <= now + timedelta(days=14),
            AppointmentSlot.id.not_in(occupied)).order_by(AppointmentSlot.starts_at, AppointmentSlot.id).limit(100))
        for slot in candidates:
            if _fits_shift(session, slot):
                slots.append(AppointmentWindow(slot_id=slot.id, starts_at=utc(slot.starts_at), ends_at=utc(slot.ends_at)))
    return AppointmentAvailability(slots=slots, appointment=appointment_read(session, active) if active else None)


def book_appointment(session, actor, ticket_id, payload, *, now=None):
    now = utc(now or datetime.now(UTC))
    ticket = owned_ticket(session, actor, ticket_id, lock=True)
    prior = session.scalar(select(CustomerAppointment).where(CustomerAppointment.user_id == actor.id, CustomerAppointment.request_id == str(payload.request_id)))
    if prior:
        if prior.ticket_id != ticket.id or prior.slot_id != str(payload.slot_id):
            raise AppointmentConflictError("This booking request ID was already used for a different selection.")
        return appointment_read(session, prior)
    if ticket.status not in ("assigned", "queued"):
        raise AppointmentConflictError("This ticket is not open for appointment booking.")
    current = active_appointment(session, ticket.id)
    candidate = session.get(AppointmentSlot, str(payload.slot_id))
    if not candidate:
        raise AppointmentConflictError("That visit window is unavailable. Please choose another time.")
    if current and current.slot_id == candidate.id:
        raise AppointmentConflictError("This visit window is already confirmed for your ticket.")
    technician_ids = {candidate.technician_id}
    if current:
        technician_ids.add(session.get(AppointmentSlot, current.slot_id).technician_id)
    # Lock physical technicians globally, not just their service-area mapping.
    list(session.scalars(select(User).where(User.id.in_(technician_ids)).order_by(User.id).with_for_update().execution_options(populate_existing=True)))
    slot = session.scalar(select(AppointmentSlot).where(AppointmentSlot.id == candidate.id).with_for_update().execution_options(populate_existing=True))
    valid = (slot.is_active and slot.technician_id in _eligible_technicians(session, ticket)
             and now + timedelta(hours=2) <= utc(slot.starts_at) <= now + timedelta(days=14)
             and _fits_shift(session, slot, lock=True))
    occupied = session.scalar(select(CustomerAppointment.id).where(CustomerAppointment.slot_id == slot.id, CustomerAppointment.status == "confirmed"))
    if not valid or occupied:
        raise AppointmentConflictError("That visit window was booked or is no longer available. Please choose another time.")
    if current and utc(session.get(AppointmentSlot, current.slot_id).starts_at) <= now + timedelta(hours=2):
        raise AppointmentConflictError("Please contact support to change a visit that starts within two hours.")
    try:
        if current:
            current.status = "cancelled"
            session.flush()
        appointment = CustomerAppointment(ticket_id=ticket.id, slot_id=slot.id, user_id=actor.id, request_id=str(payload.request_id), status="confirmed")
        session.add(appointment)
        ticket.assigned_technician_id = slot.technician_id
        ticket.status = "assigned"
        session.flush()
        session.add(AuditEvent(actor_id=actor.id, event_type="customer_appointment_rescheduled" if current else "customer_appointment_booked",
            details={"appointment_id": appointment.id, "ticket_id": ticket.id, "slot_id": slot.id, "previous_appointment_id": current.id if current else None}))
        result = appointment_read(session, appointment)
        session.commit()
        return result
    except IntegrityError as error:
        session.rollback()
        raise AppointmentConflictError("That visit window was just booked. Please choose another time.") from error


def cancel_appointment(session, actor, ticket_id, appointment_id, *, now=None):
    now = utc(now or datetime.now(UTC))
    ticket = owned_ticket(session, actor, ticket_id, lock=True)
    appointment = session.scalar(select(CustomerAppointment).where(CustomerAppointment.id == str(appointment_id), CustomerAppointment.ticket_id == ticket.id).with_for_update())
    if not appointment:
        raise AppointmentNotFoundError()
    if appointment.status == "confirmed":
        slot = session.get(AppointmentSlot, appointment.slot_id)
        if utc(slot.starts_at) <= now + timedelta(hours=2):
            raise AppointmentConflictError("Please contact support to cancel a visit that starts within two hours.")
        session.scalar(select(User).where(User.id == slot.technician_id).with_for_update())
        appointment.status = "cancelled"
        session.add(AuditEvent(actor_id=actor.id, event_type="customer_appointment_cancelled", details={"ticket_id": ticket.id, "appointment_id": appointment.id}))
    result = appointment_read(session, appointment)
    session.commit()
    return result
