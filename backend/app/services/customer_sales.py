"""Only curated, fresh offers and allowlisted official destinations leave the backend."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select

from app.domain.customer_chat_schemas import CustomerSalesOption
from app.domain.models import Customer, NetworkDevice, ProductOffer, Service, StoreLocation

STORE_URL = "https://unifi.com.my/support/find-tm-point"
SALES_URLS = {"mesh": "https://unifi.com.my/lifestyle", "plan": "https://unifi.com.my/broadband"}


def official_url(value):
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.hostname in ("unifi.com.my", "www.unifi.com.my", "selfcare.unifi.com.my")
                and url.port in (None, 443) and not url.username and not url.password and not url.fragment)
    except ValueError:
        return False


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_sales_options(session, customer_id, category, *, now=None):
    now = _utc(now or datetime.now(UTC))
    if category == "store":
        return [CustomerSalesOption(id="store-locator", name="Find a Unifi Store", description="Search by address or postcode for a store offering sales assistance.",
            official_url=STORE_URL, eligibility_note="Check the store's services and opening hours before visiting.")]
    if category not in SALES_URLS:
        return []
    customer = session.get(Customer, customer_id)
    service = session.scalar(select(Service).where(Service.customer_id == customer_id, Service.service_type == "HSI", Service.status == "active"))
    if not customer or not service:
        return []
    models = {str((device.details or {}).get("model", "")) for device in session.scalars(
        select(NetworkDevice).where(NetworkDevice.customer_id == customer_id, NetworkDevice.device_type == "router"))}
    speed = (service.details or {}).get("subscribed_download_mbps")
    offers = []
    for item in session.scalars(select(ProductOffer).where(ProductOffer.category == category, ProductOffer.is_active.is_(True), ProductOffer.is_demo == customer.is_demo).order_by(ProductOffer.code)):
        if not (official_url(item.official_url) and _utc(item.valid_from) <= now < _utc(item.valid_until)
                and now - timedelta(days=7) <= _utc(item.verified_at) <= now):
            continue
        if item.eligibility not in ("existing_customer", "check_at_checkout"):
            continue
        if item.compatible_models and not models.intersection(item.compatible_models):
            continue
        if category == "plan" and item.download_mbps and isinstance(speed, (int, float)) and item.download_mbps <= speed:
            continue
        # An unverified entitlement is a referral, never a personalized price quote.
        priced = item.eligibility == "existing_customer"
        offers.append(CustomerSalesOption(id=item.id, name=item.name, description=item.description, official_url=item.official_url,
            monthly_price_myr=item.monthly_price_myr if priced else None,
            contract_months=item.contract_months if priced else None, eligibility_note=item.eligibility_note))
    if not offers:
        offers.append(CustomerSalesOption(id=f"official-{category}", name="Mesh Wi-Fi options" if category == "mesh" else "Unifi broadband options",
            description="View current options through the official Unifi website.", official_url=SALES_URLS[category],
            eligibility_note="Confirm account eligibility, compatibility, total charges and contract terms before ordering."))
    return offers


def find_stores(session, postcode, *, now=None):
    now = _utc(now or datetime.now(UTC))
    return [dict(name=row.name, address=row.address, opening_hours=row.opening_hours, official_url=row.official_url)
        for row in session.scalars(select(StoreLocation).where(StoreLocation.postcode == postcode,
            StoreLocation.is_active.is_(True), StoreLocation.offers_sales.is_(True)).order_by(StoreLocation.name))
        if official_url(row.official_url) and now - timedelta(days=7) <= _utc(row.verified_at) <= now]
