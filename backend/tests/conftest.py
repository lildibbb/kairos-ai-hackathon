import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-only-secret")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "1024")

from app.config import Settings

# Tests must not pick up developer secrets or flags from any .env file.
Settings.model_config["env_file"] = None

from app.db.base import Base
from app.domain import models  # noqa: F401


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def enable_demo_seed(monkeypatch):
    monkeypatch.setenv("DEMO_SEED_ENABLED", "true")


@pytest.fixture
def tool_workspace(db_session: Session):
    from app.domain.models import (
        Customer,
        NetworkDevice,
        NetworkEvent,
        Role,
        Service,
        Ticket,
        User,
    )

    operator_role = Role(name="operator")
    technician_role = Role(name="technician")
    db_session.add_all([operator_role, technician_role])
    db_session.flush()

    operator = User(
        email="operator@test.invalid",
        display_name="Test Operator",
        password_hash="synthetic-test-hash",
        role_id=operator_role.id,
        is_active=True,
    )
    technician_a = User(
        email="technician-a@test.invalid",
        display_name="Technician A",
        password_hash="synthetic-test-hash",
        role_id=technician_role.id,
        is_active=True,
    )
    technician_b = User(
        email="technician-b@test.invalid",
        display_name="Technician B",
        password_hash="synthetic-test-hash",
        role_id=technician_role.id,
        is_active=True,
    )
    customer = Customer(customer_ref="CUST-1", name="Test Customer", address="1 Test Way", is_demo=True)
    other_customer = Customer(customer_ref="CUST-2", name="Other Customer", address="2 Other Way", is_demo=True)
    db_session.add_all([operator, technician_a, technician_b, customer, other_customer])
    db_session.flush()

    service = Service(
        customer_id=customer.id,
        service_type="Granite",
        service_ref="SVC-GR-1",
        status="active",
        details={},
    )
    onu = NetworkDevice(
        customer_id=customer.id,
        device_ref="DEV-ONU-1",
        device_type="ONU",
        name="Test ONU",
        status="offline",
        details={"onu_password": "Synthetic-ONU-Credential-Only-7f3!"},
    )
    router = NetworkDevice(
        customer_id=customer.id,
        device_ref="DEV-RTR-1",
        device_type="router",
        name="Test Router",
        status="unreachable",
        details={},
    )
    other_device = NetworkDevice(
        customer_id=other_customer.id,
        device_ref="DEV-RTR-2",
        device_type="router",
        name="Other Router",
        status="online",
        details={},
    )
    db_session.add_all([service, onu, router, other_device])
    db_session.flush()

    event = NetworkEvent(
        source_event_id="EVT-A",
        event_type="ONU_OFFLINE",
        device_id=onu.id,
        service_id=service.id,
        payload={},
    )
    db_session.add(event)
    db_session.flush()

    ticket = Ticket(
        source_event_id=event.id,
        customer_id=customer.id,
        service_id=service.id,
        assigned_technician_id=technician_a.id,
        severity="high",
        status="open",
        summary="ONU_OFFLINE reported for Test ONU",
    )
    db_session.add(ticket)
    db_session.commit()

    return {
        "session": db_session,
        "operator": operator,
        "technician_a": technician_a,
        "technician_b": technician_b,
        "customer": customer,
        "other_customer": other_customer,
        "onu": onu,
        "router": router,
        "other_device": other_device,
        "ticket": ticket,
    }
