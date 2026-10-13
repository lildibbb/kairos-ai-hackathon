import pytest

from app.auth.dependencies import AuthenticatedUser
from app.config import Settings
from app.services import service_orders


def _actor(workspace) -> AuthenticatedUser:
    user = workspace["technician_a"]
    return AuthenticatedUser(id=user.id, email=user.email, role="technician")


def _settings(**overrides) -> Settings:
    return Settings(database_url="sqlite://", jwt_secret="x" * 32, **overrides)


def test_order_options_follow_summarizer_actions_and_skip_slower_plans():
    options = service_orders.order_options(["mesh", "speed"], "Unifi Home Shield Essential 500Mbps + Solar Camera")

    assert [option.action for option in options] == ["mesh", "speed"]
    speeds = [product.name for product in options[1].products]
    # Same Home Shield tier first, faster than the current 500Mbps plan only.
    assert speeds[:2] == ["Unifi Home Shield Essential 1Gbps", "Unifi Home Shield Essential 2Gbps"]
    assert all(product.speed_mbps > 500 for product in options[1].products)
    assert options[1].products[0].badge == "Recommended"


def test_catalog_is_loaded_from_product_csv():
    mesh = {product.name: product.monthly_price_myr for product in service_orders.CATALOG.values() if product.action == "mesh"}
    assert mesh["Mesh Deco XE75"] == 45.0
    assert len(mesh) == 4
    assert service_orders.plan_price("Unifi Home Shield Advance 1Gbps") == 249.0


def test_no_order_options_without_actions():
    assert service_orders.order_options([], "Unifi 1Gbps") == []


def test_order_is_recorded_when_smtp_is_not_configured(db_session, tool_workspace):
    record = service_orders.submit_order(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace),
        action="mesh",
        product_code="MESH-COMBO-BOX-WI-FI-MESH-AX3000",
        notes="Living room dead zone",
        settings=_settings(),
    )

    assert record.order.status == "submitted"
    assert record.email_status == "skipped"
    assert service_orders.list_orders(db_session, tool_workspace["ticket"].id, _actor(tool_workspace))


def test_product_must_match_action(db_session, tool_workspace):
    with pytest.raises(service_orders.OrderValidationError):
        service_orders.submit_order(
            db_session,
            tool_workspace["ticket"].id,
            _actor(tool_workspace),
            action="mesh",
            product_code="PLAN-UNIFI-HOME-SHIELD-ESSENTIAL-1GBPS",
            notes=None,
            settings=_settings(),
        )


def test_order_email_is_sent_over_starttls(db_session, tool_workspace, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, username, password):
            sent["login"] = username

        def send_message(self, message):
            sent["to"] = message["To"]
            sent["subject"] = message["Subject"]

    monkeypatch.setattr(service_orders.smtplib, "SMTP", FakeSMTP)
    record = service_orders.submit_order(
        db_session,
        tool_workspace["ticket"].id,
        _actor(tool_workspace),
        action="speed",
        product_code="PLAN-UNIFI-HOME-SHIELD-ESSENTIAL-1GBPS",
        notes=None,
        settings=_settings(smtp_username="ops@example.com", smtp_password="app-pass", order_email_to="demo@example.com"),
    )

    assert record.email_status == "sent"
    assert sent == {
        "server": ("smtp.gmail.com", 587),
        "tls": True,
        "login": "ops@example.com",
        "to": "demo@example.com",
        "subject": "Order confirmation: Unifi Home Shield Essential 1Gbps",
    }
