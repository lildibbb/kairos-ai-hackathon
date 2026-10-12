from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

from app.domain.appointment_schemas import AppointmentBookingRequest
from app.domain.models import AppointmentSlot, CustomerAppointment, CustomerTroubleTicket, TechnicianShift, User, Role
from app.seed.customer_support import seed_support
from app.services.customer_appointments import availability, book_appointment, cancel_appointment, AppointmentConflictError, AppointmentNotFoundError
from test_customer_chat import workspace, ask, NOW
from test_customer_dispatch import prepare, fail_checks


def scheduled(workspace):
    session, actors = prepare(workspace)
    seed_support(session, workspace[1].model_copy(update={"demo_seed_enabled": True}), now=NOW)
    result = fail_checks(workspace)
    return session, actors, result.report.ticket_id


def payload(slot_id, request_id=None):
    return AppointmentBookingRequest(slot_id=slot_id, request_id=request_id or uuid4())


def test_confirm_retry_reschedule_cancel_and_capacity_release(workspace):
    session, actors, ticket = scheduled(workspace)
    available = availability(session, actors[0], ticket, now=NOW)
    assert available.timezone == "Asia/Kuala_Lumpur" and available.appointment is None
    assert available.slots
    request = payload(available.slots[0].slot_id)
    first = book_appointment(session, actors[0], ticket, request, now=NOW)
    assert first.status == "confirmed" and book_appointment(session, actors[0], ticket, request, now=NOW).id == first.id
    assert first.slot_id not in {slot.slot_id for slot in availability(session, actors[0], ticket, now=NOW).slots}
    second = book_appointment(session, actors[0], ticket, payload(available.slots[1].slot_id), now=NOW)
    assert session.get(CustomerAppointment, first.id).status == "cancelled"
    assert availability(session, actors[0], ticket, now=NOW).appointment.id == second.id
    cancel_appointment(session, actors[0], ticket, second.id, now=NOW)
    cancel_appointment(session, actors[0], ticket, second.id, now=NOW)
    assert availability(session, actors[0], ticket, now=NOW).appointment is None
    assert session.get(CustomerTroubleTicket, ticket).status == "assigned"
    assert first.slot_id in {slot.slot_id for slot in availability(session, actors[0], ticket, now=NOW).slots}


def test_second_customer_cannot_take_last_technician_slot(workspace):
    session, actors, first_ticket = scheduled(workspace)
    first = ask(workspace, "Slow internet on every device using Ethernet, I want to make a report.", actor=actors[1])
    second = ask(workspace, "Still not working", actor=actors[1], conversation_id=first.conversation_id, answer_choice="still_not_working")
    slot_id = availability(session, actors[0], first_ticket, now=NOW).slots[0].slot_id
    assert slot_id in {slot.slot_id for slot in availability(session, actors[1], second.report.ticket_id, now=NOW).slots}
    book_appointment(session, actors[0], first_ticket, payload(slot_id), now=NOW)
    with pytest.raises(AppointmentConflictError, match="no longer available"):
        book_appointment(session, actors[1], second.report.ticket_id, payload(slot_id), now=NOW)
    session.rollback()
    assert availability(session, actors[1], second.report.ticket_id, now=NOW).slots
    assert session.scalar(select(func.count()).select_from(CustomerAppointment).where(CustomerAppointment.status == "confirmed")) == 1


def test_customer_isolation_and_wrong_area_slot(workspace):
    session, actors, ticket = scheduled(workspace)
    with pytest.raises(AppointmentNotFoundError): availability(session, actors[1], ticket, now=NOW)
    east = session.scalar(select(User).where(User.email == "technician.east@demo.invalid"))
    slot = session.scalar(select(AppointmentSlot).where(AppointmentSlot.technician_id == east.id))
    with pytest.raises(AppointmentConflictError): book_appointment(session, actors[0], ticket, payload(slot.id), now=NOW)
    session.rollback()
    assert session.scalar(select(func.count()).select_from(CustomerAppointment)) == 0


def test_leave_inactive_technician_and_lead_time_remove_windows(workspace):
    session, actors, ticket = scheduled(workspace)
    slot = session.get(AppointmentSlot, availability(session, actors[0], ticket, now=NOW).slots[0].slot_id)
    session.add(TechnicianShift(technician_id=slot.technician_id, starts_at=slot.starts_at, ends_at=slot.reserved_until, kind="unavailable"))
    session.commit()
    assert slot.id not in {row.slot_id for row in availability(session, actors[0], ticket, now=NOW).slots}
    with pytest.raises(AppointmentConflictError): book_appointment(session, actors[0], ticket, payload(slot.id), now=NOW)
    session.rollback()
    technician = session.get(User, slot.technician_id); technician.is_active = False
    session.commit()
    assert availability(session, actors[0], ticket, now=NOW).slots == []


def test_booking_retry_id_cannot_change_selection(workspace):
    session, actors, ticket = scheduled(workspace)
    slots = availability(session, actors[0], ticket, now=NOW).slots
    first = payload(slots[0].slot_id)
    book_appointment(session, actors[0], ticket, first, now=NOW)
    with pytest.raises(AppointmentConflictError, match="different selection"):
        book_appointment(session, actors[0], ticket, payload(slots[1].slot_id, first.request_id), now=NOW)
    session.rollback()
    assert availability(session, actors[0], ticket, now=NOW).appointment.slot_id == slots[0].slot_id


def test_failed_reschedule_keeps_original_booking(workspace):
    session, actors, ticket = scheduled(workspace)
    slots = availability(session, actors[0], ticket, now=NOW).slots
    original = book_appointment(session, actors[0], ticket, payload(slots[0].slot_id), now=NOW)
    session.get(AppointmentSlot, slots[1].slot_id).is_active = False
    session.commit()
    with pytest.raises(AppointmentConflictError): book_appointment(session, actors[0], ticket, payload(slots[1].slot_id), now=NOW)
    session.rollback()
    assert availability(session, actors[0], ticket, now=NOW).appointment.id == original.id


def test_database_blocks_multiple_active_bookings_even_without_service(workspace):
    session, actors, ticket = scheduled(workspace)
    slot = availability(session, actors[0], ticket, now=NOW).slots[0].slot_id
    first = book_appointment(session, actors[0], ticket, payload(slot), now=NOW)
    session.add(CustomerAppointment(ticket_id=ticket, slot_id=slot, user_id=actors[0].id, request_id=str(uuid4()), status="confirmed"))
    with pytest.raises(IntegrityError): session.commit()
    session.rollback()
    assert availability(session, actors[0], ticket, now=NOW).appointment.id == first.id


def test_chat_history_and_followup_do_not_claim_unconfirmed_after_booking(workspace):
    from app.services.customer_chat import get_history
    session, actors, ticket = scheduled(workspace)
    record = session.get(CustomerTroubleTicket, ticket)
    slot = availability(session, actors[0], ticket, now=NOW).slots[0].slot_id
    book_appointment(session, actors[0], ticket, payload(slot), now=NOW)
    history = get_history(session, actors[0], record.conversation_id)
    assert "appointment is confirmed" in history.turns[-1].response.answer
    reply = ask(workspace, "What happens next?", conversation_id=record.conversation_id)
    assert "appointment is confirmed" in reply.answer


def test_api_bookings_are_authenticated_customer_scoped_and_operator_read_only(workspace):
    from app.auth.tokens import create_access_token
    from app.db.session import get_session
    from app.main import app
    session, actors, ticket = scheduled(workspace)
    app.dependency_overrides[get_session] = lambda: session
    token, _ = create_access_token(actors[0].id, "customer")
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/portal/me/reports/{ticket}"
    try:
        with TestClient(app) as client:
            assert client.get(f"{path}/appointment-slots").status_code == 401
            # Fixtures use fixed time; a new future window makes the endpoint test independent of wall clock.
            from datetime import datetime, UTC
            now = datetime.now(UTC)
            seed_support(session, workspace[1].model_copy(update={"demo_seed_enabled": True}), now=now)
            result = client.get(f"{path}/appointment-slots", headers=headers)
            assert result.status_code == 200
            slot = result.json()["slots"][0]["slot_id"]
            booked = client.post(f"{path}/appointments", json={"slot_id": slot, "request_id": str(uuid4())}, headers=headers)
            assert booked.status_code == 200 and booked.json()["status"] == "confirmed"
            other_token, _ = create_access_token(actors[1].id, "customer")
            assert client.get(f"{path}/appointment-slots", headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
            operator = session.scalar(select(User).join(Role).where(Role.name == "operator"))
            operator_token, _ = create_access_token(operator.id, "operator")
            assert client.get(f"{path}/appointment-slots", headers={"Authorization": f"Bearer {operator_token}"}).status_code == 403
            assert client.delete(f"{path}/appointments/{booked.json()['id']}", headers=headers).json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.clear()
