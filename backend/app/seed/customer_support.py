"""Opt-in support fixtures. Inserts new records; never refreshes old readings or resets users."""

import argparse
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.domain.models import AppointmentSlot, ProductOffer, Role, TechnicianDispatchArea, TechnicianShift, User
from app.seed.workforce_data import REFERENCE_TIME


def support_evidence(dataset):
    rows = {"wan_usage_samples": [], "wifi_radio_measurements": []}
    for index, customer in enumerate(dataset["tables"]["customers"]):
        router = next(row for row in dataset["tables"]["network_devices"] if row["customer_id"] == customer["id"] and row["device_type"] == "router")
        service = next(row for row in dataset["tables"]["services"] if row["customer_id"] == customer["id"] and row["service_type"] == "HSI")
        # Include busy and many-but-idle households. Count alone must not trigger sales.
        busy = index % 2 == 0
        for minute in (3, 2, 1):
            end = REFERENCE_TIME - timedelta(minutes=minute)
            rows["wan_usage_samples"].append(dict(id=str(uuid5(NAMESPACE_URL, f"support:{router['id']}:{minute}")), device_id=router["id"],
                window_start=end - timedelta(minutes=1), window_end=end, ingested_at=end + timedelta(seconds=5),
                download_mbps=service["details"]["subscribed_download_mbps"] * (.95 if busy else .05),
                upload_mbps=1.0, active_devices=15, source="synthetic_traffic_adapter", quality="simulated"))
        for radio in dataset["tables"]["wifi_radios"]:
            if radio["device_id"] == router["id"]:
                rows["wifi_radio_measurements"].append(dict(id=str(uuid5(NAMESPACE_URL, f"support:{radio['id']}")), radio_id=radio["id"],
                    observed_at=REFERENCE_TIME, ingested_at=REFERENCE_TIME + timedelta(seconds=5),
                    channel_utilization_pct=90 if index % 8 == 2 else 20, source="synthetic_radio_adapter", quality="simulated"))
    return rows


def seed_support(session, settings, *, now=None):
    if not settings.demo_seed_enabled:
        raise ValueError("Support fixtures require DEMO_SEED_ENABLED=true")
    now = now or datetime.now(UTC)
    count = 0
    for category, url in (("mesh", "https://unifi.com.my/lifestyle"), ("plan", "https://unifi.com.my/broadband")):
        code = f"SUPPORT-OFFICIAL-{category.upper()}"
        if not session.scalar(select(ProductOffer).where(ProductOffer.code == code)):
            session.add(ProductOffer(code=code, category=category, name="Mesh Wi-Fi options" if category == "mesh" else "Unifi broadband options",
                description="Explore current options through Unifi's official website.", official_url=url,
                eligibility="check_at_checkout", eligibility_note="Confirm eligibility, compatibility, total charges and contract terms in your Unifi account.",
                compatible_models=[], valid_from=now, valid_until=now + timedelta(days=7), verified_at=now, is_active=True, is_demo=True))
    technicians = session.scalars(select(User).join(Role).join(TechnicianDispatchArea, TechnicianDispatchArea.user_id == User.id).where(
        Role.name == "technician", User.is_demo.is_(True), User.is_active.is_(True)).distinct())
    for technician in technicians:
        local = now.astimezone(ZoneInfo("Asia/Kuala_Lumpur"))
        for offset in range(1, 6):
            day = (local + timedelta(days=offset)).replace(hour=9, minute=0, second=0, microsecond=0)
            shift_id = str(uuid5(NAMESPACE_URL, f"support-shift:{technician.id}:{day.date()}"))
            if not session.get(TechnicianShift, shift_id):
                session.add(TechnicianShift(id=shift_id, technician_id=technician.id, starts_at=day, ends_at=day.replace(hour=19), kind="working"))
            for hour in (10, 13, 16):
                start = day.replace(hour=hour)
                slot_id = str(uuid5(NAMESPACE_URL, f"support-slot:{technician.id}:{start.isoformat()}"))
                if not session.get(AppointmentSlot, slot_id):
                    # Skip a pre-existing physical window; never overwrite an imported schedule.
                    overlap = session.scalar(select(AppointmentSlot.id).where(AppointmentSlot.technician_id == technician.id, AppointmentSlot.is_active.is_(True),
                        AppointmentSlot.starts_at < start + timedelta(hours=2, minutes=30), AppointmentSlot.reserved_until > start))
                    if not overlap:
                        session.add(AppointmentSlot(id=slot_id, technician_id=technician.id, starts_at=start, ends_at=start + timedelta(hours=2),
                            reserved_until=start + timedelta(hours=2, minutes=30), is_active=True))
                        count += 1
    session.commit()
    return {"new_visit_windows": count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", action="store_true", help="Add separate historical synthetic traffic samples")
    args = parser.parse_args()
    from app.config import Settings
    from app.db.session import SessionLocal
    from app.seed.workforce_data import generate_dataset
    with SessionLocal() as session:
        settings = Settings()
        if not settings.demo_seed_enabled:
            raise ValueError("Support fixtures require DEMO_SEED_ENABLED=true")
        if args.evidence:
            from app.domain.models import Customer, NetworkDevice, WifiRadio
            from app.seed.workforce_data import ingest_support_evidence
            dataset = generate_dataset()
            owners = {row["id"] for row in dataset["tables"]["customers"]}
            if not all(session.get(Customer, key) and session.get(Customer, key).is_demo for key in owners):
                raise ValueError("Import the fictional workforce dataset first")
            rows = support_evidence(dataset)
            if not all(session.get(NetworkDevice, row["device_id"]) for row in rows["wan_usage_samples"]) or not all(session.get(WifiRadio, row["radio_id"]) for row in rows["wifi_radio_measurements"]):
                raise ValueError("Expected synthetic equipment is missing")
            print(ingest_support_evidence(session, rows))
        print(seed_support(session, settings))


if __name__ == "__main__":
    main()
