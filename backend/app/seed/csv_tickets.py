"""Remap the field-ops ticket set onto the CSV-seeded customers.

The synthetic ``MY-CUST`` seed (``app.seed.malaysia_bulk``) owns every row in
``tickets`` but never references the real Malaysian customers imported from
``customers.csv``. This module rebinds the existing tickets to those CSV
customers and deletes the leftover synthetic customers, services, devices,
events, and topology edges so ``/tickets/mine`` displays CSV-backed work.
"""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.domain.models import (
    Customer,
    CustomerSummary,
    EntityFact,
    EntityFactSheet,
    NetworkDevice,
    NetworkEvent,
    Router,
    Service,
    Ticket,
    TopologyEdge,
    User,
)
from app.seed.csv_inventory import DATA_DIR, seed_csv_inventory
from app.services.entity_facts import sync_all_facts

TECHNICIAN_EMAIL = "technician@demo.invalid"
SYNTHETIC_PREFIX = "MY-CUST%"
EVENT_FALLBACK = "CUSTOMER_REPORT"


def remap_tickets_to_csv(session: Session, data_dir: Path = DATA_DIR) -> dict[str, int]:
    seed_csv_inventory(session, data_dir)

    plans = {
        row["login_id"].strip(): row["plan_name"].strip()
        for row in _rows(data_dir / "customers.csv")
    }
    customers = list(
        session.scalars(
            select(Customer)
            .where(Customer.customer_ref.in_(plans))
            .order_by(Customer.customer_ref)
        ).all()
    )
    if not customers:
        raise ValueError("No CSV customers are present to remap tickets onto")

    technician = session.scalar(select(User).where(User.email == TECHNICIAN_EMAIL))
    if technician is None:
        raise ValueError(f"Demo technician {TECHNICIAN_EMAIL} is missing")

    services = _customer_services(session, customers, plans)
    events = _tickets_to_csv_events(session, customers, services, technician)
    removed = _remove_synthetic(session, customers)

    sync_all_facts(session)
    session.commit()
    return {"tickets": events, "customers": len(customers), **removed}


def _customer_services(
    session: Session, customers: list[Customer], plans: dict[str, str]
) -> dict[str, Service]:
    services: dict[str, Service] = {}
    for customer in customers:
        service = session.scalar(
            select(Service).where(
                Service.customer_id == customer.id, Service.service_type == "HSI"
            )
        )
        if service is None:
            service = Service(
                customer_id=customer.id,
                service_type="HSI",
                service_ref=f"HSI-{customer.account_no or customer.customer_ref}",
                status="active",
                details={"plan_name": plans[customer.customer_ref]},
            )
            session.add(service)
        else:
            service.details = {**service.details, "plan_name": plans[customer.customer_ref]}
        services[customer.customer_ref] = service
    session.flush()
    return services


def _tickets_to_csv_events(
    session: Session,
    customers: list[Customer],
    services: dict[str, Service],
    technician: User,
) -> int:
    tickets = list(session.scalars(select(Ticket).order_by(Ticket.id)).all())
    devices = _customer_devices(session, [customer.id for customer in customers])

    for index, ticket in enumerate(tickets):
        customer = customers[index % len(customers)]
        service = services[customer.customer_ref]
        device = devices.get(customer.id)
        if device is None:
            ticket.customer_id = customer.id
            ticket.service_id = service.id
            ticket.login_id = customer.customer_ref
            ticket.assigned_technician_id = technician.id
            continue

        event = NetworkEvent(
            source_event_id=f"CSV-EV-{index:05d}",
            event_type=_event_type(ticket.summary),
            device_id=device.id,
            service_id=service.id,
            payload={"reported_by": "subscriber", "source": "csv_inventory"},
        )
        session.add(event)
        session.flush()

        ticket.source_event_id = event.id
        ticket.customer_id = customer.id
        ticket.service_id = service.id
        ticket.assigned_technician_id = technician.id
        ticket.login_id = customer.customer_ref
        ticket.summary = f"{event.event_type} reported for {device.name}"
    session.flush()
    return len(tickets)


def _customer_devices(session: Session, customer_ids: list[str]) -> dict[str, NetworkDevice]:
    chosen: dict[str, NetworkDevice] = {}
    for device in session.scalars(
        select(NetworkDevice)
        .where(NetworkDevice.customer_id.in_(customer_ids))
        .order_by(NetworkDevice.customer_id, NetworkDevice.device_type)
    ).all():
        current = chosen.get(device.customer_id)
        if current is None or _device_rank(device) < _device_rank(current):
            chosen[device.customer_id] = device
    return chosen


def _device_rank(device: NetworkDevice) -> int:
    return 0 if device.device_type in ("router", "Access Point", "mesh") else 1


def _remove_synthetic(session: Session, customers: list[Customer]) -> dict[str, int]:
    keep_ids = {customer.id for customer in customers}
    synthetic_ids = [
        customer.id
        for customer in session.scalars(
            select(Customer).where(Customer.customer_ref.like(SYNTHETIC_PREFIX))
        ).all()
        if customer.id not in keep_ids
    ]
    if not synthetic_ids:
        return {"removed_customers": 0}

    service_ids = list(
        session.scalars(select(Service.id).where(Service.customer_id.in_(synthetic_ids))).all()
    )
    device_ids = list(
        session.scalars(
            select(NetworkDevice.id).where(NetworkDevice.customer_id.in_(synthetic_ids))
        ).all()
    )
    entity_ids = service_ids + device_ids

    if device_ids:
        session.execute(
            delete(TopologyEdge).where(
                or_(
                    TopologyEdge.source_device_id.in_(device_ids),
                    TopologyEdge.target_device_id.in_(device_ids),
                )
            )
        )
        session.execute(delete(NetworkEvent).where(NetworkEvent.device_id.in_(device_ids)))
        session.execute(delete(EntityFact).where(EntityFact.entity_id.in_(entity_ids)))
        session.execute(delete(EntityFactSheet).where(EntityFactSheet.entity_id.in_(entity_ids)))
        session.execute(delete(NetworkDevice).where(NetworkDevice.id.in_(device_ids)))
    session.execute(delete(Service).where(Service.id.in_(service_ids)))

    refs = list(
        session.scalars(
            select(Customer.customer_ref).where(Customer.id.in_(synthetic_ids))
        ).all()
    )
    session.execute(delete(CustomerSummary).where(CustomerSummary.login_id.in_(refs)))
    session.execute(delete(Router).where(Router.login_id.in_(refs)))
    session.execute(delete(Customer).where(Customer.id.in_(synthetic_ids)))
    session.flush()
    return {"removed_customers": len(synthetic_ids)}


def _event_type(summary: str) -> str:
    head = summary.split(" ", 1)[0].strip()
    return head.upper() if head and head.isascii() else EVENT_FALLBACK


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)
