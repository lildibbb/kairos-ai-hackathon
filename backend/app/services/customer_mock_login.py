"""Local/demo-only mocked customer portal identity.

The internal Field Force app authenticates staff against the ``users`` table.
The customer portal is a demo surface that should not share that staff login,
so it uses a mocked sign-in: a single synthetic customer identity is provisioned
lazily and no password is ever verified.

The mock identity still needs a real ``users`` row plus a ``CustomerAccount``
link because the customer-scoped chat, router-action and appointment tables all
hold NOT NULL foreign keys to ``users.id``. Provisioning keeps those constraints
and the ``(user_id, request_id)`` retry idempotency intact without exposing a
real credential.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.config import Settings
from app.domain.models import Customer, CustomerAccount, Role, User


class MockCustomerLoginDisabledError(Exception):
    pass


class MockCustomerNotFoundError(Exception):
    pass


class MockCustomerConflictError(Exception):
    pass


def provision_mock_customer(session: Session, settings: Settings) -> User:
    if not settings.customer_mock_login_enabled or settings.app_environment == "production":
        raise MockCustomerLoginDisabledError()
    customer = session.scalar(
        select(Customer).where(Customer.customer_ref == settings.customer_mock_customer_ref)
    )
    if customer is None:
        raise MockCustomerNotFoundError()

    role = session.scalar(select(Role).where(Role.name == "customer"))
    if role is None:
        role = Role(name="customer")
        session.add(role)
        session.flush()

    user = session.scalar(select(User).where(User.email == settings.customer_mock_email))
    if user is None:
        user = User(
            email=settings.customer_mock_email,
            display_name=customer.name,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role_id=role.id,
            is_active=True,
            is_demo=True,
        )
        session.add(user)
        session.flush()
    else:
        existing_role = session.get(Role, user.role_id)
        if existing_role is None or existing_role.name != "customer" or not user.is_demo or not user.is_active:
            raise MockCustomerConflictError()

    link = session.get(CustomerAccount, user.id)
    if link is None:
        session.add(CustomerAccount(user_id=user.id, customer_id=customer.id))
    elif link.customer_id != customer.id:
        raise MockCustomerConflictError()
    session.commit()
    return user
