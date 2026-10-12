from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.domain import models
from app.seed.workforce_data import SCENARIOS, generate_dataset, ingest_dataset, validate_dataset


def test_generation_is_repeatable_and_scenarios_have_consistent_observations():
    dataset = generate_dataset(customers=8)
    assert dataset == generate_dataset(customers=8)
    assert {case["scenario"] for case in dataset["evaluation_cases"]} == set(SCENARIOS)
    tables = dataset["tables"]
    for case in dataset["evaluation_cases"]:
        customer_id = case["customer_id"]
        devices = {row["device_type"]: row for row in tables["network_devices"] if row["customer_id"] == customer_id}
        services = {row["service_type"]: row for row in tables["services"] if row["customer_id"] == customer_id}
        router = _latest(tables["device_measurements"], "device_id", devices["router"]["id"])
        wifi = _latest(tables["wifi_client_measurements"], "client_device_id", devices["wifi_client"]["id"])
        if case["scenario"] == "speed_profile_mismatch":
            profile = services["HSI"]["details"]
            assert profile["subscribed_download_mbps"] == 500
            assert profile["provisioned_download_mbps"] == 100
            assert router["download_mbps"] < 100
        elif case["scenario"] == "weak_wifi":
            assert wifi["rssi_dbm"] == -79
            client = _latest(tables["device_measurements"], "device_id", devices["wifi_client"]["id"])
            assert client["download_mbps"] < router["download_mbps"]
        elif case["scenario"] == "optical_loss":
            onu = _latest(tables["device_measurements"], "device_id", devices["ONU"]["id"])
            assert onu["los_alarm"] is True
            assert onu["optical_rx_dbm"] is None
            assert router["management_reachable"] is False
            assert router["download_mbps"] == 0
            assert wifi["connected"] is True
        elif case["scenario"] == "voice_registration_failure":
            assert _latest(tables["service_measurements"], "service_id", services["VoBB"]["id"])["registration_status"] == "unregistered"
            assert _latest(tables["service_measurements"], "service_id", services["HSI"]["id"])["operational_status"] == "up"
        elif case["scenario"] == "iptv_multicast_failure":
            assert _latest(tables["service_measurements"], "service_id", services["IPTV"]["id"])["multicast_joined"] is False
        elif case["scenario"] == "stale_telemetry":
            assert router["observed_at"] < dataset["reference_time"]
            assert router["quality"] == "stale"
    for row in tables["service_measurements"]:
        service_type = next(service["service_type"] for service in tables["services"] if service["id"] == row["service_id"])
        if service_type != "VoBB":
            assert row["registration_status"] is None
        if service_type != "IPTV":
            assert row["stream_status"] is None


def test_import_is_idempotent_and_preserves_changes_after_the_demo(db_session, enable_demo_seed):
    dataset = generate_dataset(customers=8)
    first = ingest_dataset(db_session, dataset)
    router_id = next(row["id"] for row in dataset["tables"]["network_devices"] if row["device_type"] == "router")
    router = db_session.get(models.NetworkDevice, router_id)
    router.details = {**router.details, "settings": {"wifi_channel": 6}}
    ticket = db_session.get(models.Ticket, dataset["tables"]["tickets"][0]["id"])
    ticket.status = "resolved"
    db_session.commit()
    second = ingest_dataset(db_session, dataset)
    assert first["inserted"] == dataset["row_counts"]
    assert all(count == 0 for count in second["inserted"].values())
    assert second["existing"] == dataset["row_counts"]
    assert router.details["settings"]["wifi_channel"] == 6
    assert ticket.status == "resolved"
    assert db_session.scalar(select(func.count()).select_from(models.User)) == 2


def test_import_is_disabled_and_rejects_cross_customer_references(db_session, monkeypatch):
    dataset = generate_dataset(customers=2)
    monkeypatch.setenv("DEMO_SEED_ENABLED", "false")
    with pytest.raises(RuntimeError, match="DEMO_SEED_ENABLED=true"):
        ingest_dataset(db_session, dataset)
    broken = deepcopy(dataset)
    broken["tables"]["tickets"][0]["customer_id"] = broken["tables"]["customers"][1]["id"]
    with pytest.raises(ValueError, match="must agree"):
        validate_dataset(broken)
    broken = deepcopy(dataset)
    broken["tables"]["wifi_client_measurements"][0]["wifi_network_id"] = broken["tables"]["wifi_networks"][2]["id"]
    with pytest.raises(ValueError, match="within one household"):
        validate_dataset(broken)
    assert db_session.scalar(select(func.count()).select_from(models.Customer)) == 0


def test_identity_conflict_rolls_back_the_whole_import(db_session, enable_demo_seed):
    dataset = generate_dataset(customers=2)
    existing = models.Customer(
        id=dataset["tables"]["customers"][1]["id"], customer_ref="EXISTING-CUSTOMER",
        name="Existing Customer", address="Existing Address", is_demo=False,
    )
    db_session.add(existing)
    db_session.commit()
    with pytest.raises(RuntimeError, match="identity conflict"):
        ingest_dataset(db_session, dataset)
    assert db_session.scalar(select(func.count()).select_from(models.Customer)) == 1
    assert db_session.scalar(select(func.count()).select_from(models.User)) == 0
    assert db_session.get(models.Customer, existing.id).name == "Existing Customer"


def _latest(rows, field, identifier):
    return max((row for row in rows if row[field] == identifier), key=lambda row: row["observed_at"])
