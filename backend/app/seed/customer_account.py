"""Explicit local-only provisioning of a login for an existing demo household."""

import argparse
import os
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import Settings
from app.domain.models import Customer, CustomerAccount, Role, User


def create_demo_customer_account(
    session: Session,
    settings: Settings,
    *,
    customer_ref: str,
    email: str,
    password: str | None,
) -> User:
    if not settings.demo_seed_enabled:
        raise ValueError("Customer demo provisioning requires DEMO_SEED_ENABLED=true")
    customer = session.scalar(select(Customer).where(Customer.customer_ref == customer_ref))
    if customer is None or not customer.is_demo:
        raise ValueError("Select an existing fictional demo household")
    existing = session.scalar(select(User).where(User.email == email))
    if existing is not None:
        role = session.get(Role, existing.role_id)
        account = session.get(CustomerAccount, existing.id)
        if (
            not existing.is_demo or not existing.is_active or role is None or role.name != "customer"
            or account is None or account.customer_id != customer.id
        ):
            raise ValueError("Existing login does not match this demo customer; no account was changed")
        return existing
    if not password or len(password) < 12:
        raise ValueError("Choose a demo password of at least 12 characters")
    if "@" not in email or len(email) > 255:
        raise ValueError("Provide a valid demo email address")

    try:
        role = session.scalar(select(Role).where(Role.name == "customer"))
        if role is None:
            role = Role(name="customer")
            session.add(role)
            session.flush()
        user = User(
            email=email, display_name=customer.name, password_hash=hash_password(password),
            role_id=role.id, is_active=True, is_demo=True,
        )
        session.add(user)
        session.flush()
        session.add(CustomerAccount(user_id=user.id, customer_id=customer.id))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customer-ref", default="SYN-00042-0002")
    parser.add_argument("--email", default="customer@demo.invalid")
    args = parser.parse_args()
    settings = Settings()
    if not settings.demo_seed_enabled:
        parser.error("Customer demo provisioning requires DEMO_SEED_ENABLED=true")
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        password = os.environ.get("DEMO_CUSTOMER_PASSWORD")
        if password is None and session.scalar(select(User).where(User.email == args.email)) is None:
            password = getpass("Choose a local demo customer password (12+ characters): ")
        try:
            user = create_demo_customer_account(
                session, settings, customer_ref=args.customer_ref, email=args.email, password=password,
            )
        except ValueError as error:
            parser.error(str(error))
        print(f"Demo customer login ready: {user.email}; household: {args.customer_ref}")


if __name__ == "__main__":
    main()
