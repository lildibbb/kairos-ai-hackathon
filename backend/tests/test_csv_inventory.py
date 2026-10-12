from sqlalchemy import func, select

from app.domain.models import Customer, NetworkDevice, TopologyEdge
from app.seed.csv_inventory import seed_csv_inventory


def test_seed_csv_inventory_gives_every_customer_topology(db_session):
    report = seed_csv_inventory(db_session)
    assert report["customers"] > 0
    assert report["devices"] > 0

    customers = list(db_session.scalars(select(Customer)).all())
    assert customers
    for customer in customers:
        device_ids = list(
            db_session.scalars(
                select(NetworkDevice.id).where(NetworkDevice.customer_id == customer.id)
            )
        )
        edge_count = db_session.scalar(
            select(func.count()).select_from(TopologyEdge).where(
                TopologyEdge.source_device_id.in_(device_ids)
            )
        )
        assert edge_count > 0, f"{customer.customer_ref} has no topology"


def test_seed_csv_inventory_topology_is_idempotent(db_session):
    seed_csv_inventory(db_session)
    first = db_session.scalar(select(func.count()).select_from(TopologyEdge))
    seed_csv_inventory(db_session)
    assert db_session.scalar(select(func.count()).select_from(TopologyEdge)) == first
