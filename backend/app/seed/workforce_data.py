"""Generate and import fictional workforce records without resetting existing data.

Generation uses only the standard library and needs no database or API keys.
Import requires DEMO_SEED_ENABLED=true and the normal Alembic migrations.
"""

import argparse
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "seed" / "generated" / "workforce.json"
KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "seed" / "workforce_knowledge"
REFERENCE_TIME = datetime(2026, 10, 12, 1, 0, tzinfo=UTC)
TECHNICIAN_EMAIL = "technician@demo.invalid"
SCENARIOS = (
    "healthy", "weak_wifi", "wifi_interference", "speed_profile_mismatch",
    "optical_loss", "voice_registration_failure", "iptv_multicast_failure", "stale_telemetry",
)
COMPLAINTS = {
    "healthy": "My connection briefly stopped earlier. It seems to be working again now.",
    "weak_wifi": "The Internet works near the router, but my laptop is slow in the bedroom.",
    "wifi_interference": "Wi-Fi keeps slowing down and disconnecting even near the router.",
    "speed_profile_mismatch": "My plan was upgraded, but a wired speed test is still much slower.",
    "optical_loss": "Internet, home phone and TV stopped together. The optical box has a red LOS light.",
    "voice_registration_failure": "Internet works, but my home phone cannot make or receive calls.",
    "iptv_multicast_failure": "Internet and phone work, but the TV channels will not load.",
    "stale_telemetry": "My connection is slow right now. Can you check it again?",
}
TABLES = (
    "customers", "services", "network_devices", "topology_edges", "wifi_radios", "wifi_networks",
    "device_measurements", "wifi_client_measurements", "service_measurements", "network_events", "tickets",
)
REFERENCES = {
    "services": {"customer_id": "customers"},
    "network_devices": {"customer_id": "customers"},
    "topology_edges": {"source_device_id": "network_devices", "target_device_id": "network_devices", "service_id": "services"},
    "wifi_radios": {"device_id": "network_devices"},
    "wifi_networks": {"radio_id": "wifi_radios"},
    "device_measurements": {"device_id": "network_devices"},
    "wifi_client_measurements": {"client_device_id": "network_devices", "wifi_network_id": "wifi_networks"},
    "service_measurements": {"service_id": "services"},
    "network_events": {"device_id": "network_devices", "service_id": "services"},
    "tickets": {"source_event_id": "network_events", "customer_id": "customers", "service_id": "services"},
}
IDENTITY_FIELDS = {
    "customers": ("customer_ref", "is_demo"),
    "services": ("customer_id", "service_ref", "service_type"),
    "network_devices": ("customer_id", "device_ref", "device_type"),
    "topology_edges": ("source_device_id", "target_device_id", "service_id"),
    "wifi_radios": ("device_id", "band_ghz"),
    "wifi_networks": ("radio_id", "bssid"),
    "device_measurements": ("device_id",),
    "wifi_client_measurements": ("client_device_id", "wifi_network_id"),
    "service_measurements": ("service_id",),
    "network_events": ("source_event_id", "device_id", "service_id"),
    "tickets": ("source_event_id", "customer_id", "service_id"),
}


def generate_dataset(customers: int = 20, seed: int = 42) -> dict:
    if not 1 <= customers <= 500:
        raise ValueError("customers must be between 1 and 500")
    if not 0 <= seed <= 65535:
        raise ValueError("seed must be between 0 and 65535")
    rng = random.Random(seed)
    tables = {name: [] for name in TABLES}
    evaluations = []
    for number in range(1, customers + 1):
        scenario = SCENARIOS[(number - 1) % len(SCENARIOS)]
        prefix = f"SYN-{seed:05d}-{number:04d}"
        customer_id = _id(prefix)
        down, up = rng.choice(((100, 50), (300, 100), (500, 100)))
        applied_down = 100 if scenario == "speed_profile_mismatch" else down
        if scenario == "speed_profile_mismatch":
            down, up = 500, 100
        tables["customers"].append({
            "id": customer_id, "customer_ref": prefix, "name": f"Fictional Household {number:04d}",
            "address": f"{number} Demo Street, Fictional District {1 + (number - 1) // 10}, Example City",
            "is_demo": True,
        })
        services = {}
        for kind in ("Granite", "HSI", "VoBB", "IPTV"):
            ref = f"{prefix}-{kind.upper()}"
            services[kind] = _id(ref)
            details = {"is_synthetic": True}
            if kind == "HSI":
                details.update({
                    "subscribed_download_mbps": down, "subscribed_upload_mbps": up,
                    "provisioned_download_mbps": applied_down, "provisioned_upload_mbps": up,
                    "profile_ref": f"DEMO-PROFILE-{down}-{up}", "provisioning_version": 1,
                })
            elif kind == "VoBB":
                details["service_number"] = f"DEMO-VOICE-{number:04d}"
            elif kind == "IPTV":
                details["subscriber_ref"] = f"DEMO-TV-{number:04d}"
            tables["services"].append({
                "id": services[kind], "customer_id": customer_id, "service_type": kind,
                "service_ref": ref, "status": "active", "details": details,
            })

        devices = {}
        for offset, (kind, label) in enumerate((("OLT", "Access node"), ("ONU", "Optical unit"), ("router", "Home router"), ("wifi_client", "Laptop"))):
            ref = f"{prefix}-{kind.upper()}"
            devices[kind] = _id(ref)
            status = "offline" if scenario == "optical_loss" and kind == "ONU" else "online"
            if scenario == "optical_loss" and kind == "router":
                status = "unreachable"
            last_seen = REFERENCE_TIME - timedelta(hours=2) if scenario == "stale_telemetry" else REFERENCE_TIME
            tables["network_devices"].append({
                "id": devices[kind], "customer_id": customer_id, "device_ref": ref,
                "device_type": kind, "name": f"Demo {label} {number:04d}", "status": status,
                "details": {
                    "is_synthetic": True, "mac_address": _mac(seed, number, offset),
                    "manufacturer": "Fictional Network Labs", "model": f"DEMO-{kind.upper()}-V1",
                    "serial_number": ref, "firmware_version": "demo-1.0", "platform": "DEMO_OS",
                    "ip_address": "192.168.0.1" if kind == "router" else None,
                    "topology_role": "root" if kind == "OLT" else "child",
                    "last_seen_at": last_seen.isoformat(),
                },
            })
        for parent, child, service, link in (
            ("OLT", "ONU", "Granite", "fiber"), ("ONU", "router", "HSI", "ethernet"),
            ("router", "wifi_client", "HSI", "wireless"),
        ):
            tables["topology_edges"].append({
                "id": _id(f"{prefix}-LINK-{parent}-{child}"), "source_device_id": devices[parent],
                "target_device_id": devices[child], "service_id": services[service], "link_type": link,
            })
        networks = {}
        for offset, (band, channel, width) in enumerate(((2.4, 11, 40), (5.0, 44, 80))):
            radio_id = _id(f"{prefix}-RADIO-{band}")
            network_id = _id(f"{prefix}-WIFI-{band}")
            networks[band] = network_id
            tables["wifi_radios"].append({
                "id": radio_id, "device_id": devices["router"], "band_ghz": band,
                "channel": channel, "channel_width_mhz": width,
                "antenna_configuration": "2x2", "wifi_standard": "802.11ax",
            })
            tables["wifi_networks"].append({
                "id": network_id, "radio_id": radio_id,
                "ssid": f"DEMO-{seed}-{number:04d}-{int(band * 10)}", "bssid": _mac(seed, number, 10 + offset),
            })
        for sample in range(3):
            _measurements(tables, prefix, scenario, sample, devices, services, networks, down, up, applied_down, rng)

        event_id = _id(f"{prefix}-REPORT")
        ticket_id = _id(f"{prefix}-TICKET")
        affected = "VoBB" if scenario == "voice_registration_failure" else "IPTV" if scenario == "iptv_multicast_failure" else "Granite" if scenario == "optical_loss" else "HSI"
        tables["network_events"].append({
            "id": event_id, "source_event_id": f"{prefix}-REPORT", "event_type": "CUSTOMER_REPORT",
            "device_id": devices["ONU"] if affected == "Granite" else devices["router"],
            "service_id": services[affected], "received_at": REFERENCE_TIME.isoformat(),
            "processed_at": REFERENCE_TIME.isoformat(),
            "payload": {
                "is_synthetic": True, "channel": "customer_chat", "reported_symptom": COMPLAINTS[scenario],
                "reported_at": REFERENCE_TIME.isoformat(), "ticket_number": f"{prefix}-TICKET",
                "activity_ref": f"{prefix}-CTT", "observation_source": "customer_report",
            },
        })
        tables["tickets"].append({
            "id": ticket_id, "source_event_id": event_id, "customer_id": customer_id,
            "service_id": services[affected], "assigned_technician_email": TECHNICIAN_EMAIL,
            "severity": "high" if scenario == "optical_loss" else "low" if scenario == "healthy" else "medium",
            "status": "open", "summary": COMPLAINTS[scenario],
        })
        evaluations.append({
            "customer_id": customer_id, "ticket_id": ticket_id, "scenario": scenario,
            "expected_action": "propose_sync_speed_profile" if scenario == "speed_profile_mismatch" else
            "refresh_telemetry" if scenario == "stale_telemetry" else "escalate_optical_loss" if scenario == "optical_loss" else "diagnose_before_changing_configuration",
            "forbidden_actions": ["factory_reset", "change_subscription", "execute_without_staff_approval"],
        })
    dataset = {
        "schema_version": 1, "is_synthetic": True, "random_seed": seed,
        "reference_time": REFERENCE_TIME.isoformat(), "tables": tables,
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "evaluation_cases": evaluations,
    }
    validate_dataset(dataset)
    return dataset


def _measurements(tables, prefix, scenario, sample, devices, services, networks, down, up, applied_down, rng):
    faulty = sample > 0
    loss = scenario == "optical_loss" and faulty
    stale = scenario == "stale_telemetry"
    observed = REFERENCE_TIME - timedelta(minutes=(2 - sample) * 30 + (120 if stale else 0))
    common = {
        "observed_at": observed.isoformat(),
        "ingested_at": (REFERENCE_TIME if stale else observed + timedelta(seconds=5)).isoformat(),
        "source": "synthetic_device_adapter", "quality": "stale" if stale else "simulated",
    }
    wired_down = 0.0 if loss else round((applied_down if faulty else down) * rng.uniform(0.88, 0.94), 1)
    weak = scenario == "weak_wifi" and faulty
    interference = scenario == "wifi_interference" and faulty
    wifi_down = 0.0 if loss else round(min(wired_down, rng.uniform(8, 20) if weak else rng.uniform(20, 40) if interference else down * 0.7), 1)
    for kind in ("ONU", "router", "wifi_client"):
        row = {
            "id": _id(f"{prefix}-MEASURE-{kind}-{sample}"), "device_id": devices[kind], **common,
            "operational_status": "offline" if loss and kind == "ONU" else "unreachable" if loss and kind == "router" else "online",
            "management_reachable": False if loss and kind in ("ONU", "router") else None if kind == "wifi_client" else True,
            "wan_status": "down" if loss else "up",
            "uptime_seconds": None if loss and kind == "ONU" else 86400 + sample * 1800,
            "los_alarm": loss if kind == "ONU" else None,
            "optical_rx_dbm": round(rng.uniform(-22, -19), 1) if kind == "ONU" and not loss else None,
            "optical_tx_dbm": 2.1 if kind == "ONU" and not loss else None,
            "test_connection": "wired" if kind == "router" else "wifi" if kind == "wifi_client" else None,
            "download_mbps": wired_down if kind == "router" else wifi_down if kind == "wifi_client" else None,
            "upload_mbps": 0.0 if loss and kind != "ONU" else round(up * 0.9, 1) if kind != "ONU" else None,
            "latency_ms": None if loss or kind == "ONU" else 80.0 if kind == "wifi_client" and interference else 12.0,
            "packet_loss_pct": 100.0 if loss and kind != "ONU" else 8.0 if kind == "wifi_client" and interference else 0.0,
            "disconnect_count_24h": 6 * sample if interference and kind == "wifi_client" else sample if loss else 0,
            "disconnect_count_7d": 18 + 6 * sample if interference and kind == "wifi_client" else sample if loss else 0,
        }
        if kind == "wifi_client" and (weak or interference) and not loss:
            row["upload_mbps"] = min(row["upload_mbps"], wifi_down)
        tables["device_measurements"].append(row)
    tables["wifi_client_measurements"].append({
        "id": _id(f"{prefix}-CLIENT-MEASURE-{sample}"), "client_device_id": devices["wifi_client"],
        "wifi_network_id": networks[5.0], **common, "connected": True,
        "rssi_dbm": -79.0 if weak else -48.0, "snr_db": 12.0 if weak else 14.0 if interference else 35.0,
        "tx_link_mbps": 36.0 if weak else 144.0 if interference else 866.0,
        "rx_link_mbps": 36.0 if weak else 144.0 if interference else 866.0,
        "retry_pct": 40.0 if interference else 18.0 if weak else 2.0,
    })
    for kind in ("HSI", "VoBB", "IPTV"):
        voice_fault = scenario == "voice_registration_failure" and faulty and kind == "VoBB"
        tv_fault = scenario == "iptv_multicast_failure" and faulty and kind == "IPTV"
        tables["service_measurements"].append({
            "id": _id(f"{prefix}-SERVICE-MEASURE-{kind}-{sample}"), "service_id": services[kind], **common,
            "operational_status": "down" if loss or voice_fault or tv_fault else "up",
            "registration_status": ("unregistered" if loss or voice_fault else "registered") if kind == "VoBB" else None,
            "stream_status": ("unavailable" if loss or tv_fault else "playing") if kind == "IPTV" else None,
            "multicast_joined": not (loss or tv_fault) if kind == "IPTV" else None,
            "vlan_id": 600 if kind == "IPTV" else 400 if kind == "VoBB" else 500,
            "jitter_ms": None if loss else 3.0, "packet_loss_pct": None if loss else 0.0,
            "last_error": "upstream_optical_loss" if loss else "registration_failed" if voice_fault else "multicast_join_failed" if tv_fault else None,
        })


def _id(reference: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"synthetic-workforce-v1/{reference}"))


def _mac(seed: int, customer: int, offset: int) -> str:
    return f"02:{seed >> 8:02x}:{seed & 255:02x}:{customer >> 8:02x}:{customer & 255:02x}:{offset:02x}"


def validate_dataset(dataset: dict) -> None:
    if dataset.get("schema_version") != 1 or dataset.get("is_synthetic") is not True:
        raise ValueError("Only version 1 explicitly synthetic workforce datasets are supported")
    tables = dataset.get("tables", {})
    if set(tables) != set(TABLES):
        raise ValueError("Dataset must contain exactly the documented workforce tables")
    ids = {}
    for name, rows in tables.items():
        ids[name] = {row["id"] for row in rows}
        if len(ids[name]) != len(rows) or dataset.get("row_counts", {}).get(name) != len(rows):
            raise ValueError(f"Duplicate IDs or incorrect row count in {name}")
        for row in rows:
            if name == "customers" and (row.get("is_demo") is not True or not row.get("customer_ref", "").startswith("SYN-")):
                raise ValueError("All imported customers must be explicitly synthetic")
            if name == "tickets" and row.get("assigned_technician_email") != TECHNICIAN_EMAIL:
                raise ValueError("Synthetic tickets must use the documented demo technician")
            for field, value in row.items():
                if field.endswith("_at") and value is not None:
                    parsed = datetime.fromisoformat(value)
                    if parsed.tzinfo is None:
                        raise ValueError(f"{name}.{field} must include a timezone")
    for name, fields in REFERENCES.items():
        for row in tables[name]:
            for field, target in fields.items():
                if row.get(field) not in ids[target]:
                    raise ValueError(f"Broken reference: {name}.{field} -> {target}")
    records = {name: {row["id"]: row for row in rows} for name, rows in tables.items()}
    devices = records["network_devices"]
    services = records["services"]
    for row in tables["topology_edges"]:
        owner = devices[row["source_device_id"]]["customer_id"]
        if owner != devices[row["target_device_id"]]["customer_id"] or owner != services[row["service_id"]]["customer_id"]:
            raise ValueError("Synthetic topology links must stay within one household")
    for row in tables["wifi_client_measurements"]:
        network = records["wifi_networks"][row["wifi_network_id"]]
        radio = records["wifi_radios"][network["radio_id"]]
        if devices[row["client_device_id"]]["customer_id"] != devices[radio["device_id"]]["customer_id"]:
            raise ValueError("Wi-Fi client measurements must stay within one household")
    for row in tables["network_events"]:
        if devices[row["device_id"]]["customer_id"] != services[row["service_id"]]["customer_id"]:
            raise ValueError("Report device and service must belong to the same household")
    for row in tables["tickets"]:
        event = records["network_events"][row["source_event_id"]]
        if row["customer_id"] != services[row["service_id"]]["customer_id"] or row["service_id"] != event["service_id"]:
            raise ValueError("Ticket customer, service and report must agree")


def ingest_dataset(session, dataset: dict) -> dict[str, dict[str, int]]:
    from sqlalchemy import select
    from app.config import Settings
    from app.domain import models

    if not Settings().demo_seed_enabled:
        raise RuntimeError("Set DEMO_SEED_ENABLED=true for this local synthetic import")
    validate_dataset(dataset)
    report = {"inserted": {}, "existing": {}}
    try:
        technician_id = _ensure_demo_accounts(session)
        for name in TABLES:
            model = next(item for item in models.Base.registry.mappers if item.local_table.name == name).class_
            report["inserted"][name] = report["existing"][name] = 0
            existing_rows = {
                row.id: row for row in session.scalars(select(model).where(model.id.in_([row["id"] for row in dataset["tables"][name]]))).all()
            }
            for original in dataset["tables"][name]:
                values = dict(original)
                if name == "tickets":
                    values.pop("assigned_technician_email")
                    values["assigned_technician_id"] = technician_id
                for field, value in values.items():
                    if field.endswith("_at") and value is not None:
                        values[field] = datetime.fromisoformat(value)
                existing = existing_rows.get(values["id"])
                if existing is not None:
                    if any(getattr(existing, field) != values[field] for field in IDENTITY_FIELDS[name]):
                        raise RuntimeError(f"Synthetic import identity conflict in {name}: {values['id']}")
                    report["existing"][name] += 1
                else:
                    session.add(model(**values))
                    report["inserted"][name] += 1
            session.flush()
        session.commit()
    except Exception:
        session.rollback()
        raise
    return report


def _ensure_demo_accounts(session) -> str:
    from argon2 import PasswordHasher
    from sqlalchemy import select
    from app.domain.models import Role, User
    from app.seed.demo_data import DEMO_ACCOUNTS

    technician_id = None
    for email, role_name in (("operator@demo.invalid", "operator"), (TECHNICIAN_EMAIL, "technician")):
        role = session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name)
            session.add(role)
            session.flush()
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=f"Demo {role_name.title()}",
                        password_hash=PasswordHasher().hash(DEMO_ACCOUNTS[email]), role_id=role.id,
                        is_active=True, is_demo=True)
            session.add(user)
            session.flush()
        if not user.is_demo or not user.is_active or user.role_id != role.id:
            raise RuntimeError(f"Existing account {email} is not an active demo {role_name}")
        if role_name == "technician":
            technician_id = user.id
    return technician_id


def ingest_support_evidence(session, rows):
    from app.config import Settings
    from app.domain.models import Customer, NetworkDevice, WanUsageSample, WifiRadio, WifiRadioMeasurement
    if not Settings().demo_seed_enabled:
        raise ValueError("Support evidence requires DEMO_SEED_ENABLED=true")
    inserted = 0
    try:
        for name, model in (("wan_usage_samples", WanUsageSample), ("wifi_radio_measurements", WifiRadioMeasurement)):
            for row in rows[name]:
                if row["quality"] != "simulated" or not row["source"].startswith("synthetic_"):
                    raise ValueError("Synthetic evidence must remain marked simulated")
                device_id = row.get("device_id")
                if name == "wifi_radio_measurements":
                    radio = session.get(WifiRadio, row["radio_id"])
                    device_id = radio.device_id if radio else None
                device = session.get(NetworkDevice, device_id) if device_id else None
                customer = session.get(Customer, device.customer_id) if device else None
                if not customer or not customer.is_demo:
                    raise ValueError("Support evidence can only reference fictional customer equipment")
                if not session.get(model, row["id"]):
                    session.add(model(**row))
                    inserted += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"new_support_measurements": inserted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Write a repeatable, fictional JSON dataset")
    generate.add_argument("--customers", type=int, default=20)
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ingest = commands.add_parser("ingest", help="Insert the JSON dataset into the configured database")
    ingest.add_argument("--input", type=Path, default=DEFAULT_OUTPUT)
    commands.add_parser("index-knowledge", help="Embed the separate synthetic troubleshooting procedures")
    args = parser.parse_args()
    if args.command == "generate":
        dataset = generate_dataset(args.customers, args.seed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
        print(f"Generated {args.customers} fictional households at {args.output.resolve()}")
        print(json.dumps(dataset["row_counts"], sort_keys=True))
        return
    from app.db.session import SessionLocal
    if args.command == "ingest":
        dataset = json.loads(args.input.read_text(encoding="utf-8"))
        with SessionLocal() as session:
            report = ingest_dataset(session, dataset)
        print(json.dumps(report, sort_keys=True))
    else:
        from app.ai.ingestion import index_knowledge
        from app.config import get_settings
        from app.integrations.embeddings import build_embedding_provider
        with SessionLocal() as session:
            report = index_knowledge(session, build_embedding_provider(get_settings()), directory=KNOWLEDGE_DIR)
            session.commit()
        print(f"Indexed {report.documents} workforce documents, {report.chunks} chunks; generated {report.embeddings_generated} embeddings")


if __name__ == "__main__":
    main()
