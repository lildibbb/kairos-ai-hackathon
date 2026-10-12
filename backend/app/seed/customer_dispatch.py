"""Opt-in fictional area mappings. Never resets accounts or overwrites existing mappings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import Settings
from app.domain.models import Customer, CustomerDispatchArea, DispatchArea, Role, TechnicianDispatchArea, User


def seed_dispatch(session: Session, settings: Settings) -> dict:
    if not settings.demo_seed_enabled:
        raise ValueError("Dispatch demo seed requires DEMO_SEED_ENABLED=true")
    role = session.scalar(select(Role).where(Role.name == "technician"))
    if role is None:
        raise ValueError("Import the synthetic workforce dataset first")
    areas = {}
    for code, name, email in (
        ("DEMO-WEST", "Demo West", "technician@demo.invalid"),
        ("DEMO-EAST", "Demo East", "technician.east@demo.invalid"),
    ):
        area = session.scalar(select(DispatchArea).where(DispatchArea.code == code))
        if area and not area.is_demo:
            raise ValueError("Existing area is not a demo area; no mappings changed")
        if not area:
            area = DispatchArea(code=code, name=name, is_active=True, is_demo=True)
            session.add(area)
            session.flush()
        user = session.scalar(select(User).where(User.email == email))
        if not user:
            user = User(email=email, display_name=f"{name} Technician",
                password_hash=hash_password("Demo-Technician-Only-2026!"), role_id=role.id, is_active=True, is_demo=True)
            session.add(user)
            session.flush()
        if not user.is_demo or user.role_id != role.id or not user.is_active:
            raise ValueError("Existing technician is not an active demo technician; no account changed")
        if session.get(TechnicianDispatchArea, (user.id, area.id)) is None:
            session.add(TechnicianDispatchArea(user_id=user.id, area_id=area.id, is_available=True))
        areas[code] = area
    count = 0
    for number in range(1, 21):
        customer = session.scalar(select(Customer).where(Customer.customer_ref == f"SYN-00042-{number:04d}"))
        if not customer or not customer.is_demo:
            continue
        if session.get(CustomerDispatchArea, customer.id) is None:
            code = "DEMO-WEST" if number <= 10 else "DEMO-EAST"
            session.add(CustomerDispatchArea(customer_id=customer.id, area_id=areas[code].id))
            count += 1
    session.commit()
    return {"new_customer_mappings": count, "areas": [area.code for area in areas.values()]}


def main():
    from app.db.session import SessionLocal
    with SessionLocal() as session:
        print(seed_dispatch(session, Settings()))


if __name__ == "__main__":
    main()
