"""Import the supplied Malaysian customers, devices, and routers CSV files."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Customer, NetworkDevice, Router, Service, TopologyEdge

DATA_DIR = Path(__file__).resolve().parents[1]


def seed_csv_inventory(session: Session, data_dir: Path = DATA_DIR) -> dict[str, int]:
    customers = _seed_customers(session, data_dir / "customers.csv")
    session.flush()
    devices = _seed_devices(session, data_dir / "devices.csv", customers)
    routers = _seed_routers(session, data_dir / "routers.csv", customers)
    topology_edges = _seed_topology(session, customers)
    session.commit()
    return {
        "customers": len(customers),
        "devices": devices,
        "routers": routers,
        "topology_edges": topology_edges,
    }


def _seed_customers(session: Session, path: Path) -> dict[str, Customer]:
    indexed: dict[str, Customer] = {}
    for row in _rows(path):
        login_id = row["login_id"].strip()
        customer = session.scalar(select(Customer).where(Customer.customer_ref == login_id))
        values = {
            "customer_ref": login_id,
            "name": row["name"].strip(),
            "address": row["address"].strip(),
            "is_demo": False,
            "account_no": row["account_no"].strip(),
            "contact_no": row["contact_no"].strip(),
            "email_address": row["email_address"].strip(),
            "contract_term": int(row["contract_term"]),
            "commitment_start": _date(row["commitment_start"]),
            "commitment_end": _date(row["commitment_end"]),
        }
        if customer is None:
            customer = Customer(**values)
            session.add(customer)
        else:
            for key, value in values.items():
                setattr(customer, key, value)
        indexed[login_id] = customer
    return indexed


def _seed_devices(session: Session, path: Path, customers: dict[str, Customer]) -> int:
    count = 0
    for row in _rows(path):
        customer = customers.get(row["login_id"].strip())
        if customer is None:
            continue
        device_ref = row["mac_address"].strip()
        device = session.scalar(select(NetworkDevice).where(NetworkDevice.device_ref == device_ref))
        values = {
            "customer_id": customer.id,
            "login_id": row["login_id"].strip(),
            "device_ref": device_ref,
            "device_type": row["device_type"].strip(),
            "name": row["friendly_name"].strip() or device_ref,
            "status": "online",
            "details": {"source": "devices.csv"},
            "mac_address": device_ref,
            "friendly_name": row["friendly_name"].strip(),
            "manufacturer": row["manufacturer"].strip(),
            "brand": row["brand"].strip(),
            "cloud_device_type": row["cloud_device_type"].strip(),
            "link_type": row["link_type"].strip(),
            "ip_address": row["ip_address"].strip() or None,
            "ssid_2_4ghz": row["ssid_2_4ghz"].strip() or None,
            "ssid_5ghz": row["ssid_5ghz"].strip() or None,
            "channel_2_4ghz": _int(row["channel_2_4ghz"]),
            "channel_5ghz": _int(row["channel_5ghz"]),
            "antenna_2_4ghz": row["antenna_2_4ghz"].strip() or None,
            "antenna_5ghz": row["antenna_5ghz"].strip() or None,
            "protocol_2_4ghz": row["protocol_2_4ghz"].strip() or None,
            "protocol_5ghz": row["protocol_5ghz"].strip() or None,
            "rssi": _int(row["rssi"]),
            "rx_rate": _int(row["rx_rate"]),
            "tx_rate": _int(row["tx_rate"]),
            "platform": row["platform"].strip() or None,
            "parent_mac": row["parent_mac"].strip() or None,
            "bandwidth_2_4ghz": row["bandwidth_2_4ghz"].strip() or None,
            "bandwidth_5ghz": row["bandwidth_5ghz"].strip() or None,
        }
        if device is None:
            device = NetworkDevice(**values)
            session.add(device)
        else:
            for key, value in values.items():
                setattr(device, key, value)
        count += 1
    return count


def _seed_routers(session: Session, path: Path, customers: dict[str, Customer]) -> int:
    count = 0
    for row in _rows(path):
        login_id = row["login_id"].strip()
        if login_id not in customers:
            continue
        serial = row["serial_number"].strip()
        router = session.get(Router, serial)
        values = {
            "serial_number": serial,
            "login_id": login_id,
            "manufacturer": row["manufacturer"].strip(),
            "model": row["model"].strip(),
            "cpu_usage_pct": _int(row["cpu_usage_pct"]),
            "cpu_temperature_c": _int(row["cpu_temperature_c"]),
            "memory_usage_pct": _int(row["memory_usage_pct"]),
            "monthly_usage_gb": _float(row["monthly_usage_gb"]),
            "rx_power_dbm": _float(row["rx_power_dbm"]),
        }
        if router is None:
            session.add(Router(**values))
        else:
            for key, value in values.items():
                setattr(router, key, value)
        count += 1
    return count


def _seed_topology(session: Session, customers: dict[str, Customer]) -> int:
    count = 0
    for customer in customers.values():
        devices = list(
            session.scalars(
                select(NetworkDevice).where(NetworkDevice.customer_id == customer.id)
            ).all()
        )
        by_mac = {device.mac_address: device for device in devices if device.mac_address}
        service = session.scalar(
            select(Service).where(Service.customer_id == customer.id, Service.service_type == "HSI")
        )
        service_id = service.id if service is not None else None
        for device in devices:
            parent = by_mac.get(device.parent_mac) if device.parent_mac else None
            if parent is None or parent.id == device.id:
                continue
            existing = session.scalar(
                select(TopologyEdge).where(
                    TopologyEdge.source_device_id == parent.id,
                    TopologyEdge.target_device_id == device.id,
                )
            )
            if existing is None:
                session.add(
                    TopologyEdge(
                        source_device_id=parent.id,
                        target_device_id=device.id,
                        service_id=service_id,
                        link_type=_link_type(device.link_type),
                    )
                )
                count += 1
    session.flush()
    return count


def _link_type(value: str) -> str:
    return "ethernet" if value.strip().lower() == "ethernet" else "wireless"


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def _date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%d/%m/%Y %H:%M:%S")


def _int(value: str) -> int | None:
    return int(value) if value.strip() else None


def _float(value: str) -> float | None:
    return float(value) if value.strip() else None
