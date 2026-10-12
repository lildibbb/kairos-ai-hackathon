"""Explicitly stage a fictional VLAN mismatch in isolated showcase state."""

import argparse

from sqlalchemy import select

from app.config import Settings
from app.domain.models import Customer, CustomerRouterAction, CustomerRouterState, NetworkDevice, Service
from app.services.customer_router_actions import SIMULATED_VLANS


def stage_vlan_mismatch(session, settings, *, customer_ref, service_type, vlan_id):
    if not settings.demo_seed_enabled or not settings.customer_router_simulation_enabled or settings.app_environment == "production":
        raise ValueError("Explicit development/test seeding and router simulation must be enabled")
    if service_type not in SIMULATED_VLANS or not 1 <= vlan_id <= 4094:
        raise ValueError("Select a supported service and VLAN between 1 and 4094")
    customer = session.scalar(select(Customer).where(Customer.customer_ref == customer_ref).with_for_update())
    if not customer or not customer.is_demo:
        raise ValueError("Select an existing fictional household")
    routers = list(session.scalars(select(NetworkDevice).where(NetworkDevice.customer_id == customer.id,
        NetworkDevice.device_type == "router").with_for_update()))
    if len(routers) != 1 or not (routers[0].details or {}).get("is_synthetic"):
        raise ValueError("Select a household with exactly one synthetic router")
    device = routers[0]
    from datetime import UTC, datetime
    if session.scalar(select(CustomerRouterAction.id).where(CustomerRouterAction.device_id == device.id,
        CustomerRouterAction.status == "pending", CustomerRouterAction.expires_at > datetime.now(UTC))):
        raise ValueError("Cancel the pending router action before staging a mismatch")
    services = list(session.scalars(select(Service.service_type).where(Service.customer_id == customer.id,
        Service.status == "active", Service.service_type.in_(SIMULATED_VLANS))))
    if service_type not in services:
        raise ValueError("The household does not have that active service")
    state = session.get(CustomerRouterState, device.id)
    if state is None:
        state = CustomerRouterState(device_id=device.id, reboot_count=0,
            service_vlans={key: SIMULATED_VLANS[key] for key in services})
        session.add(state)
    state.service_vlans = {**state.service_vlans, service_type: vlan_id}
    session.commit()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customer-ref", required=True)
    parser.add_argument("--service", choices=tuple(SIMULATED_VLANS), required=True)
    parser.add_argument("--vlan", type=int, required=True)
    args = parser.parse_args()
    from app.db.session import SessionLocal
    with SessionLocal() as session:
        try:
            stage_vlan_mismatch(session, Settings(), customer_ref=args.customer_ref,
                service_type=args.service, vlan_id=args.vlan)
        except ValueError as error:
            parser.error(str(error))
    print(f"Staged simulated {args.service} VLAN {args.vlan} for {args.customer_ref}; physical equipment unchanged.")


if __name__ == "__main__":
    main()
