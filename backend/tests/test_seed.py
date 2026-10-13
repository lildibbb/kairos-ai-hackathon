import pytest
from argon2 import PasswordHasher
from pydantic import ValidationError
from sqlalchemy import func, select

from app.domain.models import (
    AssistantMessage, AssistantSession, AuditEvent, Customer, EntityFact,
    EntityFactSheet, KnowledgeChunk, KnowledgeDocument, NetworkDevice,
    NetworkEvent, Role, Service, Ticket, ToolExecution, TopologyEdge, User,
)
from app.config import Settings
from app.seed.demo_data import DEMO_ACCOUNTS, DEMO_EVENT_SOURCE_IDS, seed_demo_data


def test_seed_is_idempotent_and_contains_expected_demo_records(db_session, enable_demo_seed):
    seed_demo_data(db_session)
    counts_after_first_run = _seed_counts(db_session)

    seed_demo_data(db_session)
    counts_after_second_run = _seed_counts(db_session)

    assert counts_after_first_run == {
        "users": 2,
        "customers": 2,
        "services": 8,
        "network_devices": 24,
        "topology_edges": 22,
        "network_events": 10,
        "pending_events": 10,
        "tickets": 0,
        "knowledge_documents": 8,
        "knowledge_chunks": 42,
        "entity_facts": 166,
        "entity_fact_sheets": 26,
        "assistant_sessions": 0,
        "assistant_messages": 0,
        "tool_executions": 0,
        "audit_events": 0,
    }
    assert counts_after_second_run == counts_after_first_run

    users = {user.email: user for user in db_session.scalars(select(User).where(User.email.in_(DEMO_ACCOUNTS))).all()}
    assert set(users) == set(DEMO_ACCOUNTS)
    assert all(user.password_hash.startswith("$argon2id$") for user in users.values())
    assert all(PasswordHasher().verify(user.password_hash, DEMO_ACCOUNTS[email]) for email, user in users.items())
    roles = {role.id: role.name for role in db_session.scalars(select(Role)).all()}
    assert roles[users["operator@demo.invalid"].role_id] == "operator"
    assert roles[users["technician@demo.invalid"].role_id] == "technician"
    assert all(user.is_active for user in users.values())


def test_unrelated_pending_event_does_not_fail_seed_verification(db_session, enable_demo_seed):
    seed_demo_data(db_session)
    device = db_session.scalar(select(NetworkDevice).where(NetworkDevice.device_ref == "MY-ONT-001"))
    db_session.add(NetworkEvent(
        source_event_id="UNRELATED-PENDING-EVENT-001",
        event_type="UNRELATED_TEST_EVENT",
        device_id=device.id,
        payload={"test": True},
    ))
    db_session.commit()

    assert seed_demo_data(db_session) == {"pending_events": 10, "demo_accounts": 2}
    assert _count(db_session, NetworkEvent) == 11
    assert _count(db_session, NetworkEvent, NetworkEvent.processed_at.is_(None)) == 11
    assert _count(db_session, NetworkEvent, _seeded_pending_event_filter()) == 10


def test_seed_fails_clearly_on_divergent_demo_row(db_session, enable_demo_seed):
    seed_demo_data(db_session)
    device = db_session.scalar(select(NetworkDevice).where(NetworkDevice.device_ref == "MY-ONT-001"))
    device.status = "online"
    db_session.commit()

    with pytest.raises(RuntimeError, match="Seed conflict.*MY-ONT-001.*status"):
        seed_demo_data(db_session)

    db_session.refresh(device)
    assert device.status == "online"


def test_seed_is_disabled_by_default(db_session, monkeypatch):
    monkeypatch.delenv("DEMO_SEED_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="DEMO_SEED_ENABLED=true"):
        seed_demo_data(db_session)
    assert _count(db_session, User) == 0


def test_embedding_dimensions_follow_configured_model_size():
    assert Settings(database_url="sqlite://", jwt_secret="test").embedding_dimensions == 1024
    assert Settings(
        database_url="sqlite://", jwt_secret="test", embedding_dimensions=4096
    ).embedding_dimensions == 4096
    with pytest.raises(ValidationError, match="positive integer"):
        Settings(database_url="sqlite://", jwt_secret="test", embedding_dimensions=0)


def test_seed_rolls_back_partial_writes_after_verification_failure(db_session, enable_demo_seed):
    operator_role = Role(name="operator")
    db_session.add(operator_role)
    db_session.flush()
    db_session.add(User(
        email="operator@demo.invalid",
        display_name="Diverged Operator",
        password_hash=PasswordHasher().hash("synthetic-test-password"),
        role_id=operator_role.id,
        is_active=True,
        is_demo=True,
    ))
    db_session.commit()

    with pytest.raises(RuntimeError, match="Seed conflict.*operator@demo.invalid"):
        seed_demo_data(db_session)

    assert db_session.scalar(select(Role).where(Role.name == "technician")) is None
    assert _count(db_session, Customer) == 0


def _count(session, model, criterion=None):
    statement = select(func.count()).select_from(model)
    if criterion is not None:
        statement = statement.where(criterion)
    return session.scalar(statement)


def _seed_counts(session):
    return {
        "users": _count(session, User),
        "customers": _count(session, Customer),
        "services": _count(session, Service),
        "network_devices": _count(session, NetworkDevice),
        "topology_edges": _count(session, TopologyEdge),
        "network_events": _count(session, NetworkEvent),
        "pending_events": _count(session, NetworkEvent, _seeded_pending_event_filter()),
        "tickets": _count(session, Ticket),
        "knowledge_documents": _count(session, KnowledgeDocument),
        "knowledge_chunks": _count(session, KnowledgeChunk),
        "entity_facts": _count(session, EntityFact),
        "entity_fact_sheets": _count(session, EntityFactSheet),
        "assistant_sessions": _count(session, AssistantSession),
        "assistant_messages": _count(session, AssistantMessage),
        "tool_executions": _count(session, ToolExecution),
        "audit_events": _count(session, AuditEvent),
    }


def _seeded_pending_event_filter():
    return (
        NetworkEvent.source_event_id.in_(DEMO_EVENT_SOURCE_IDS)
        & NetworkEvent.processed_at.is_(None)
    )
