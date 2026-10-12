"""Opt-in PostgreSQL checks, isolated in a disposable schema, never public tables."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.base import Base
from app.domain.models import AppointmentSlot, CustomerAppointment
from app.services.customer_appointments import AppointmentConflictError, availability, book_appointment
from test_customer_appointments import payload, scheduled
from test_customer_chat import NOW, ask, workspace


pytestmark = pytest.mark.skipif(
    os.environ.get("APPOINTMENT_POSTGRES_TESTS") != "1",
    reason="Set APPOINTMENT_POSTGRES_TESTS=1 with an explicit PostgreSQL DATABASE_URL",
)


@pytest.fixture
def db_session():
    url = os.environ["DATABASE_URL"]
    if not url.startswith("postgresql"):
        pytest.fail("These concurrency tests require PostgreSQL")
    engine = create_engine(url, connect_args={"options": "-c lock_timeout=10000 -c statement_timeout=20000"})
    schema = f"appointment_test_{uuid4().hex}"
    isolated = engine.execution_options(schema_translate_map={None: schema})
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        Base.metadata.create_all(isolated)
        with Session(isolated, expire_on_commit=False) as session:
            yield session
    finally:
        # Only this test's generated schema is removed, even after a failed test.
        assert schema.startswith("appointment_test_") and len(schema) == 49
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def race_bookings(session, requests):
    engine = session.get_bind()
    session.rollback()
    barrier = Barrier(len(requests))

    def reserve(request):
        actor, ticket, slot = request
        with Session(engine, expire_on_commit=False) as transaction:
            barrier.wait(timeout=10)
            try:
                return book_appointment(transaction, actor, ticket, payload(slot), now=NOW).status
            except AppointmentConflictError:
                transaction.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        futures = [executor.submit(reserve, request) for request in requests]
        return [future.result(timeout=30) for future in futures]


def second_ticket(workspace, actor):
    first = ask(workspace, "Slow internet on every device using Ethernet, I want to make a report.", actor=actor)
    return ask(workspace, "Still not working", actor=actor, conversation_id=first.conversation_id,
        answer_choice="still_not_working").report.ticket_id


def test_two_customers_racing_for_one_slot_have_one_winner(workspace):
    session, actors, ticket = scheduled(workspace)
    other_ticket = second_ticket(workspace, actors[1])
    slot = availability(session, actors[0], ticket, now=NOW).slots[0].slot_id
    assert slot in {row.slot_id for row in availability(session, actors[1], other_ticket, now=NOW).slots}
    assert sorted(race_bookings(session, [(actors[0], ticket, slot), (actors[1], other_ticket, slot)])) == ["confirmed", "conflict"]
    assert session.scalar(select(func.count()).select_from(CustomerAppointment).where(CustomerAppointment.status == "confirmed")) == 1


def test_competing_reservations_for_one_ticket_keep_one_active_booking(workspace):
    session, actors, ticket = scheduled(workspace)
    slots = availability(session, actors[0], ticket, now=NOW).slots
    assert race_bookings(session, [(actors[0], ticket, slots[0].slot_id), (actors[0], ticket, slots[1].slot_id)]) == ["confirmed", "confirmed"]
    # The second transaction is an atomic reschedule, not a second active visit.
    assert session.scalar(select(func.count()).select_from(CustomerAppointment).where(CustomerAppointment.status == "confirmed")) == 1
    assert session.scalar(select(func.count()).select_from(CustomerAppointment).where(CustomerAppointment.status == "cancelled")) == 1


def test_database_rejects_overlapping_physical_windows_including_travel_buffer(workspace):
    session, actors, ticket = scheduled(workspace)
    slot = session.get(AppointmentSlot, availability(session, actors[0], ticket, now=NOW).slots[0].slot_id)
    technician, reserved_until = slot.technician_id, slot.reserved_until
    session.add(AppointmentSlot(technician_id=technician, starts_at=slot.ends_at + timedelta(minutes=15),
        ends_at=reserved_until + timedelta(minutes=15), reserved_until=reserved_until + timedelta(minutes=15), is_active=True))
    with pytest.raises(IntegrityError) as failure:
        session.commit()
    assert failure.value.orig.diag.constraint_name == "ex_technician_slot_overlap"
    session.rollback()
    adjacent = AppointmentSlot(technician_id=technician, starts_at=reserved_until,
        ends_at=reserved_until + timedelta(minutes=30), reserved_until=reserved_until + timedelta(minutes=30), is_active=True)
    session.add(adjacent)
    session.commit()
    assert session.get(AppointmentSlot, adjacent.id) is not None
