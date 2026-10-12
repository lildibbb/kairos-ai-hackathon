from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.dependencies import AuthenticatedUser
from app.auth.passwords import verify_password
from app.auth.tokens import create_access_token
from app.config import Settings
from app.db.session import get_session
from app.domain.models import (
    CustomerAccount, DeviceMeasurement, NetworkDevice, Service, ServiceMeasurement,
    Ticket, User, WifiClientMeasurement, WifiNetwork, WifiRadio,
)
from app.main import app
from app.seed.customer_account import create_demo_customer_account
from app.seed.workforce_data import REFERENCE_TIME, generate_dataset, ingest_dataset
from app.services.customer_diagnostics import CustomerAccountNotFoundError, get_my_diagnostics

PASSWORD = "Synthetic customer password!"
NOW = REFERENCE_TIME + timedelta(minutes=5)


@pytest.fixture
def portal_workspace(db_session, enable_demo_seed):
    settings = Settings(demo_seed_enabled=True)
    dataset = generate_dataset(customers=8)
    ingest_dataset(db_session, dataset)
    user = create_demo_customer_account(
        db_session, settings, customer_ref="SYN-00042-0002",
        email="customer@demo.invalid", password=PASSWORD,
    )
    actor = AuthenticatedUser(id=user.id, email=user.email, role="customer")
    return db_session, dataset, user, actor


@pytest.fixture
def portal_client(portal_workspace):
    session, _, user, _ = portal_workspace
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            token, _ = create_access_token(user.id, "customer")
            yield client, {"Authorization": f"Bearer {token}"}
    finally:
        app.dependency_overrides.clear()


def test_returns_latest_household_readings_and_no_secrets(portal_workspace):
    session, dataset, _, actor = portal_workspace
    customer_id = dataset["tables"]["customers"][1]["id"]
    router = session.scalar(select(NetworkDevice).where(
        NetworkDevice.customer_id == customer_id, NetworkDevice.device_type == "router",
    ))
    router.details = {**router.details, "router_password": "do-not-expose-device-secret"}
    internet = session.scalar(select(Service).where(Service.customer_id == customer_id, Service.service_type == "HSI"))
    internet.details = {**internet.details, "iptv_password": "do-not-expose-service-secret"}
    session.commit()
    ticket_count = session.scalar(select(func.count()).select_from(Ticket))

    result = get_my_diagnostics(session, actor, now=NOW)
    assert result.customer_ref == "SYN-00042-0002"
    assert len(result.devices) == 4 and len(result.services) == 4
    assert len(result.wifi_networks) == 2 and len(result.wifi_clients) == 1
    assert result.wifi_clients[0].latest_measurement.rssi_dbm == -79
    assert result.wifi_clients[0].latest_measurement.observed_at == REFERENCE_TIME
    assert result.wifi_clients[0].latest_measurement.freshness == "fresh"
    assert result.wifi_clients[0].latest_measurement.age_seconds == 300
    assert result.requires_follow_up is True
    profile = next(service.speed_profile for service in result.services if service.service_type == "HSI")
    assert profile.subscribed_download_mbps == internet.details["subscribed_download_mbps"]
    assert "do-not-expose" not in result.model_dump_json()
    assert "password" not in result.model_dump_json()
    other_ids = {row["id"] for row in dataset["tables"]["network_devices"] if row["customer_id"] != customer_id}
    assert not other_ids.intersection(device.id for device in result.devices)
    assert session.scalar(select(func.count()).select_from(Ticket)) == ticket_count
    assert not session.new and not session.dirty and not session.deleted


def test_customer_can_login_and_cannot_select_another_household(portal_client, portal_workspace):
    client, headers = portal_client
    _, dataset, user, _ = portal_workspace
    login = client.post("/auth/login", data={"username": user.email, "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["role"] == "customer"
    own = client.get("/portal/me/diagnostics", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert own.status_code == 200
    attempted_override = client.get(
        "/portal/me/diagnostics", params={"customer_id": dataset["tables"]["customers"][0]["id"]}, headers=headers,
    )
    assert attempted_override.status_code == 200
    assert attempted_override.json()["customer_ref"] == "SYN-00042-0002"
    assert client.get("/portal/me/diagnostics").status_code == 401
    assert client.get("/portal/me/diagnostics", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_customer_cannot_use_staff_routes_and_staff_cannot_use_portal(portal_client, portal_workspace):
    client, headers = portal_client
    session, dataset, _, _ = portal_workspace
    ticket_id = dataset["tables"]["tickets"][0]["id"]
    customer_id = dataset["tables"]["customers"][0]["id"]
    assert client.get("/tickets/mine", headers=headers).status_code == 403
    assert client.get(f"/tickets/{ticket_id}", headers=headers).status_code == 403
    assert client.get(f"/customers/{customer_id}", headers=headers).status_code == 403
    staff = session.scalar(select(User).where(User.email == "technician@demo.invalid"))
    token, _ = create_access_token(staff.id, "technician")
    assert client.get("/portal/me/diagnostics", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_unlinked_inactive_and_wrong_role_accounts_are_rejected(portal_client, portal_workspace):
    client, headers = portal_client
    session, _, user, actor = portal_workspace
    link = session.get(CustomerAccount, user.id)
    session.delete(link)
    session.commit()
    assert client.get("/portal/me/diagnostics", headers=headers).status_code == 403
    with pytest.raises(CustomerAccountNotFoundError):
        get_my_diagnostics(session, actor, now=NOW)
    user.is_active = False
    session.commit()
    assert client.get("/portal/me/diagnostics", headers=headers).status_code == 401
    with pytest.raises(CustomerAccountNotFoundError):
        get_my_diagnostics(session, actor, now=NOW)
    with pytest.raises(HTTPException):
        get_my_diagnostics(session, AuthenticatedUser(id=user.id, email=user.email, role="operator"), now=NOW)


def test_stale_and_missing_readings_are_not_healthy(portal_workspace):
    session, dataset, user, actor = portal_workspace
    link = session.get(CustomerAccount, user.id)
    link.customer_id = dataset["tables"]["customers"][7]["id"]
    session.commit()
    stale = get_my_diagnostics(session, actor, now=NOW)
    assert stale.wifi_clients[0].latest_measurement.freshness == "stale"
    assert "stale_measurement" in {warning.code for warning in stale.warnings}
    assert stale.requires_follow_up is True

    device_ids = [device.id for device in stale.devices]
    service_ids = [service.id for service in stale.services]
    session.query(DeviceMeasurement).filter(DeviceMeasurement.device_id.in_(device_ids)).delete(synchronize_session=False)
    session.query(WifiClientMeasurement).filter(WifiClientMeasurement.client_device_id.in_(device_ids)).delete(synchronize_session=False)
    session.query(ServiceMeasurement).filter(ServiceMeasurement.service_id.in_(service_ids)).delete(synchronize_session=False)
    session.commit()
    missing = get_my_diagnostics(session, actor, now=NOW)
    assert all(device.latest_measurement is None for device in missing.devices)
    assert all(service.latest_measurement is None for service in missing.services)
    codes = {warning.code for warning in missing.warnings}
    assert {"missing_device_measurement", "missing_service_measurement", "missing_wifi_measurement"} <= codes
    assert missing.requires_follow_up is True


def test_future_times_bad_quality_and_missing_metrics_are_flagged(portal_workspace):
    session, dataset, _, actor = portal_workspace
    customer_id = dataset["tables"]["customers"][1]["id"]
    router = session.scalar(select(NetworkDevice).where(NetworkDevice.customer_id == customer_id, NetworkDevice.device_type == "router"))
    reading = session.scalar(select(DeviceMeasurement).where(DeviceMeasurement.device_id == router.id).order_by(DeviceMeasurement.observed_at.desc()))
    reading.observed_at = NOW + timedelta(minutes=1)
    reading.ingested_at = NOW + timedelta(minutes=2)
    reading.quality = "unknown"
    reading.download_mbps = None
    session.commit()
    result = get_my_diagnostics(session, actor, now=NOW)
    observation = next(device.latest_measurement for device in result.devices if device.id == router.id)
    assert observation.freshness == "invalid"
    assert observation.download_mbps is None
    codes = {warning.code for warning in result.warnings}
    assert {"invalid_measurement_time", "unverified_measurement_quality", "incomplete_measurement"} <= codes


def test_latest_wifi_association_must_have_both_customer_owned_endpoints(portal_workspace):
    session, dataset, _, actor = portal_workspace
    own_customer_id = dataset["tables"]["customers"][1]["id"]
    other_customer_id = dataset["tables"]["customers"][0]["id"]
    own_client = session.scalar(select(NetworkDevice).where(NetworkDevice.customer_id == own_customer_id, NetworkDevice.device_type == "wifi_client"))
    other_client = session.scalar(select(NetworkDevice).where(NetworkDevice.customer_id == other_customer_id, NetworkDevice.device_type == "wifi_client"))
    other_network = session.scalar(select(WifiNetwork).join(WifiRadio).join(NetworkDevice).where(NetworkDevice.customer_id == other_customer_id))
    own_network = session.scalar(select(WifiNetwork).join(WifiRadio).join(NetworkDevice).where(NetworkDevice.customer_id == own_customer_id))
    for client_id, network_id in ((own_client.id, other_network.id), (other_client.id, own_network.id)):
        session.add(WifiClientMeasurement(
            client_device_id=client_id, wifi_network_id=network_id,
            observed_at=NOW - timedelta(seconds=10), ingested_at=NOW - timedelta(seconds=5),
            source="bad-import", quality="good", connected=True, rssi_dbm=-1,
        ))
    session.commit()
    result = get_my_diagnostics(session, actor, now=NOW)
    assert result.wifi_clients == []
    assert "unavailable_wifi_association" in {warning.code for warning in result.warnings}
    assert other_client.id not in result.model_dump_json()
    assert other_network.id not in result.model_dump_json()


def test_numeric_profiles_are_sanitized_without_exposing_json(portal_workspace):
    session, dataset, _, actor = portal_workspace
    service = session.scalar(select(Service).where(
        Service.customer_id == dataset["tables"]["customers"][1]["id"], Service.service_type == "HSI",
    ))
    service.details = {
        "subscribed_download_mbps": "NaN", "subscribed_upload_mbps": True,
        "provisioned_download_mbps": -1, "provisioned_upload_mbps": "100",
        "password": "never-export-this",
    }
    session.commit()
    result = get_my_diagnostics(session, actor, now=NOW)
    profile = next(item.speed_profile for item in result.services if item.service_type == "HSI")
    assert profile.model_dump() == {
        "subscribed_download_mbps": None, "subscribed_upload_mbps": None,
        "provisioned_download_mbps": None, "provisioned_upload_mbps": 100,
    }
    assert "never-export-this" not in result.model_dump_json()
    assert "missing_speed_profile" in {warning.code for warning in result.warnings}


def test_customer_provisioning_is_guarded_idempotent_and_never_rebinds(portal_workspace):
    session, _, user, _ = portal_workspace
    settings = Settings(demo_seed_enabled=True)
    original_hash = user.password_hash
    same = create_demo_customer_account(
        session, settings, customer_ref="SYN-00042-0002", email=user.email, password="Different password!",
    )
    assert same.id == user.id and same.password_hash == original_hash
    assert verify_password(PASSWORD, same.password_hash)
    with pytest.raises(ValueError, match="no account was changed"):
        create_demo_customer_account(session, settings, customer_ref="SYN-00042-0001", email=user.email, password=PASSWORD)
    with pytest.raises(ValueError, match="DEMO_SEED_ENABLED"):
        create_demo_customer_account(session, Settings(demo_seed_enabled=False), customer_ref="SYN-00042-0002", email="other@demo.invalid", password=PASSWORD)
    with pytest.raises(ValueError, match="12 characters"):
        create_demo_customer_account(session, settings, customer_ref="SYN-00042-0002", email="other@demo.invalid", password="short")
    assert session.scalar(select(func.count()).select_from(CustomerAccount)) == 1
    assert session.get(CustomerAccount, user.id).customer_id == session.scalar(select(Service.customer_id).where(Service.service_ref == "SYN-00042-0002-HSI"))


def test_no_hosted_model_or_embedding_is_required(portal_client, monkeypatch):
    client, headers = portal_client
    def fail(*args, **kwargs):
        raise AssertionError("Diagnostics must not invoke a model or embedding provider")
    monkeypatch.setattr("app.integrations.model_provider.HostedChatCompletionProvider.complete", fail)
    monkeypatch.setattr("app.integrations.embeddings.HostedEmbeddingProvider.embed_query", fail)
    assert client.get("/portal/me/diagnostics", headers=headers).status_code == 200
