"""Read-only diagnostics scoped to the authenticated customer's account link."""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser
from app.auth.policy import require_role
from app.config import get_settings
from app.domain.diagnostic_schemas import (
    CustomerDiagnosticsRead,
    DiagnosticDeviceRead,
    DiagnosticServiceRead,
    DiagnosticWarningRead,
    DiagnosticWifiClientRead,
    DiagnosticWifiNetworkRead,
    DeviceObservationRead,
    ServiceObservationRead,
    SpeedProfileRead,
    WifiObservationRead,
    WanUsageRead,
    WifiRadioObservationRead,
)
from app.domain.models import (
    Customer,
    CustomerAccount,
    DeviceMeasurement,
    NetworkDevice,
    Role,
    Service,
    ServiceMeasurement,
    User,
    WifiClientMeasurement,
    WifiNetwork,
    WifiRadio,
    WanUsageSample,
    WifiRadioMeasurement,
)


class CustomerAccountNotFoundError(Exception):
    pass


def get_my_diagnostics(
    session: Session,
    actor: AuthenticatedUser,
    *,
    now: datetime | None = None,
) -> CustomerDiagnosticsRead:
    require_role(actor.role, ("customer",))
    customer = session.scalar(
        select(Customer)
        .join(CustomerAccount, CustomerAccount.customer_id == Customer.id)
        .join(User, User.id == CustomerAccount.user_id)
        .join(Role, Role.id == User.role_id)
        .where(User.id == actor.id, User.is_active.is_(True), Role.name == "customer")
    )
    if customer is None:
        raise CustomerAccountNotFoundError()

    checked_at = _utc(now or datetime.now(UTC))
    max_age = get_settings().diagnostic_max_age_seconds
    warnings = []
    if customer.is_demo:
        _warn(warnings, "demo_data", None, "This is a fictional demo household, not live customer telemetry.")

    services = list(session.scalars(
        select(Service).where(Service.customer_id == customer.id).order_by(Service.service_type, Service.id)
    ))
    devices = list(session.scalars(
        select(NetworkDevice).where(NetworkDevice.customer_id == customer.id).order_by(NetworkDevice.id)
    ))
    device_ids = [device.id for device in devices]
    device_readings = _latest(session, DeviceMeasurement, "device_id", device_ids)
    service_readings = _latest(session, ServiceMeasurement, "service_id", [service.id for service in services])
    networks = session.execute(
        select(WifiNetwork, WifiRadio)
        .join(WifiRadio, WifiRadio.id == WifiNetwork.radio_id)
        .where(WifiRadio.device_id.in_(device_ids))
        .order_by(WifiNetwork.id)
    ).all()
    network_ids = [network.id for network, _ in networks]
    router_ids = [device.id for device in devices if device.device_type == "router"]
    usage_rows = list(session.scalars(select(WanUsageSample).where(
        WanUsageSample.device_id.in_(router_ids),
        WanUsageSample.window_end >= checked_at - timedelta(seconds=max_age),
    ).order_by(WanUsageSample.window_end.desc()).limit(60)))
    radio_rows = _latest(session, WifiRadioMeasurement, "radio_id", [radio.id for _, radio in networks])
    client_readings = _latest(session, WifiClientMeasurement, "client_device_id", device_ids)

    service_results = []
    for service in services:
        reading = service_readings.get(service.id)
        profile = None
        if service.service_type == "HSI":
            profile = SpeedProfileRead(**{
                key: _speed((service.details or {}).get(key)) for key in SpeedProfileRead.model_fields
            })
            if any(value is None for value in profile.model_dump().values()):
                _warn(warnings, "missing_speed_profile", service.id, "Some subscribed or provisioned speed values are unknown.")
        if reading is None and service.service_type in ("HSI", "VoBB", "IPTV"):
            _warn(warnings, "missing_service_measurement", service.id, "No operational service reading is available.")
        observation = _observation(ServiceObservationRead, reading, checked_at, max_age, warnings, service.id)
        if reading is not None:
            required = ("operational_status",)
            if service.service_type == "VoBB":
                required += ("registration_status",)
            elif service.service_type == "IPTV":
                required += ("stream_status", "multicast_joined")
            _check_missing(reading, required, warnings, service.id)
        service_results.append(DiagnosticServiceRead(
            id=service.id, service_type=service.service_type, subscription_status=service.status,
            speed_profile=profile, latest_measurement=observation,
        ))

    device_results = []
    for device in devices:
        reading = device_readings.get(device.id)
        if reading is None and device.device_type in ("router", "ONU", "wifi_client"):
            _warn(warnings, "missing_device_measurement", device.id, "No operational device reading is available.")
        if reading is not None:
            required = ("operational_status",)
            if device.device_type == "router":
                required += ("wan_status", "download_mbps", "upload_mbps")
            elif device.device_type == "ONU":
                required += ("los_alarm",)
            _check_missing(reading, required, warnings, device.id)
        device_results.append(DiagnosticDeviceRead(
            id=device.id, device_type=device.device_type, name=device.name, inventory_status=device.status,
            latest_measurement=_observation(DeviceObservationRead, reading, checked_at, max_age, warnings, device.id),
        ))

    wifi_clients = []
    for device in devices:
        reading = client_readings.get(device.id)
        if reading is None:
            if device.device_type == "wifi_client":
                _warn(warnings, "missing_wifi_measurement", device.id, "No customer-owned Wi-Fi connection reading is available.")
            continue
        if reading.wifi_network_id not in network_ids:
            _warn(warnings, "unavailable_wifi_association", device.id, "The latest Wi-Fi association cannot be verified within this household.")
            continue
        if reading.connected:
            _check_missing(reading, ("rssi_dbm", "snr_db"), warnings, device.id)
        wifi_clients.append(DiagnosticWifiClientRead(
            client_device_id=device.id, wifi_network_id=reading.wifi_network_id,
            latest_measurement=_observation(WifiObservationRead, reading, checked_at, max_age, warnings, device.id),
        ))

    if not any(service.service_type == "HSI" for service in services):
        _warn(warnings, "missing_internet_service", None, "No Internet subscription record is available.")
    for kind in ("router", "ONU"):
        if not any(device.device_type == kind for device in devices):
            _warn(warnings, "missing_equipment", None, f"No {kind} inventory record is available.")
    if not networks:
        _warn(warnings, "missing_wifi_configuration", None, "No customer-owned Wi-Fi configuration is available.")

    return CustomerDiagnosticsRead(
        customer_ref=customer.customer_ref, customer_name=customer.name, installation_address=customer.address,
        is_demo=customer.is_demo, checked_at=checked_at, max_age_seconds=max_age,
        services=service_results, devices=device_results, wifi_clients=wifi_clients,
        wifi_networks=[DiagnosticWifiNetworkRead(
            id=network.id, router_device_id=radio.device_id, ssid=network.ssid, band_ghz=radio.band_ghz,
            channel=radio.channel, channel_width_mhz=radio.channel_width_mhz,
            antenna_configuration=radio.antenna_configuration, wifi_standard=radio.wifi_standard,
        ) for network, radio in networks],
        wan_usage=[_observation(WanUsageRead, row, checked_at, max_age, warnings, row.device_id) for row in usage_rows],
        radio_measurements=[_observation(WifiRadioObservationRead, row, checked_at, max_age, warnings, row.radio_id) for row in radio_rows.values()],
        warnings=warnings,
    )


def _latest(session, model, key, ids):
    if not ids:
        return {}
    # Rank in SQL so only the latest snapshot per scoped entity is loaded.
    ranked = select(
        model.id,
        func.row_number().over(
            partition_by=getattr(model, key),
            order_by=(model.observed_at.desc(), model.ingested_at.desc(), model.id.desc()),
        ).label("position"),
    ).where(getattr(model, key).in_(ids)).subquery()
    rows = session.scalars(select(model).join(ranked, ranked.c.id == model.id).where(ranked.c.position == 1))
    return {getattr(row, key): row for row in rows}


def _observation(schema, row, now, max_age, warnings, resource_id):
    if row is None:
        return None
    observed_at, ingested_at = _utc(row.observed_at), _utc(row.ingested_at)
    age = (now - observed_at).total_seconds()
    freshness = "fresh"
    if age < 0 or ingested_at > now or ingested_at < observed_at:
        freshness = "invalid"
        _warn(warnings, "invalid_measurement_time", resource_id, "The observation has inconsistent or future timestamps.")
    elif age > max_age or row.quality.lower() == "stale":
        freshness = "stale"
        _warn(warnings, "stale_measurement", resource_id, "This reading is old or marked stale; it is not proof of current conditions.")
    if row.quality.lower() not in ("good", "simulated", "stale"):
        _warn(warnings, "unverified_measurement_quality", resource_id, "The quality of this reading is not confirmed.")
    if row.quality.lower() == "simulated" and not any(item.code == "simulated_measurements" for item in warnings):
        _warn(warnings, "simulated_measurements", None, "Some readings are simulated and must not be presented as live tests.")
    values = {key: getattr(row, key) for key in schema.model_fields if key not in ("age_seconds", "freshness")}
    if "window_start" in values:
        values["window_start"] = _utc(values["window_start"])
    values.update(observed_at=observed_at, ingested_at=ingested_at, age_seconds=age, freshness=freshness)
    return schema.model_validate(values)


def _check_missing(row, keys, warnings, resource_id):
    missing = [key for key in keys if getattr(row, key) is None or getattr(row, key) in ("", "unknown")]
    if missing:
        _warn(warnings, "incomplete_measurement", resource_id, f"Unknown reading fields: {', '.join(missing)}.")


def _speed(value):
    if isinstance(value, bool) or not isinstance(value, (float, int, str)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _utc(value):
    # SQLite tests return naive timestamps; persisted PostgreSQL timestamps are timezone-aware.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _warn(warnings, code, resource_id, message):
    warnings.append(DiagnosticWarningRead(code=code, resource_id=resource_id, message=message))
