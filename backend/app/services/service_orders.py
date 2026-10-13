"""Order actions offered from a ticket's AI summary, and their submission.

summarize.py decides which order actions a ticket gets (``mesh``, ``speed``,
``reboot``). This module turns each action into orderable products, records the
submitted order, and e-mails a confirmation over SMTP (Gmail by default).
"""

from __future__ import annotations

import csv
import html
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser
from app.config import Settings
from app.domain.models import AuditEvent, Customer, ServiceOrder
from app.services import ticket_queries

ORDER_ACTIONS = ("mesh", "speed", "reboot", "replace")
ACTION_LABELS = {
    "mesh": "Add mesh Wi-Fi coverage",
    "speed": "Upgrade internet plan",
    "reboot": "Remote router reboot",
    "replace": "Replace router if the reboot does not fix it",
}


@dataclass(frozen=True)
class OrderProduct:
    code: str
    action: str
    name: str
    description: str
    monthly_price_myr: float | None = None
    one_time_price_myr: float | None = None
    speed_mbps: int | None = None
    tier: str | None = None
    features: tuple[str, ...] = ()
    badge: str | None = None


PRODUCT_CSV = Path(__file__).resolve().parents[1] / "product.csv"

_TIER_FEATURES = {
    "Essential": "Home Shield Essential",
    "Advance": "Home Shield Advance",
    "Premium": "Home Shield Premium",
}
# Public Wi-Fi standards of the mesh hardware named in product.csv.
_MESH_DETAILS = {
    "decobe65": ("Wi-Fi 7", "Tri-band BE9300 mesh for large or multi-storey homes", "Best coverage"),
    "decoxe75": ("Wi-Fi 6E", "Tri-band AXE5400 mesh with a 6 GHz backhaul", "Great value"),
    "ax3000 2.5g": ("Wi-Fi 6", "AX3000 combo mesh box with a 2.5G Ethernet port", None),
    "ax3000": ("Wi-Fi 6", "AX3000 combo mesh box", "Lowest price"),
}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", text.upper()).strip("-")


def _speed(name: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(G|M)bps", name, re.I)
    if not match:
        return None
    value = float(match.group(1))
    return int(value * 1000) if match.group(2).upper() == "G" else int(value)


def _mesh_product(name: str, price: float) -> OrderProduct:
    key = name.lower().replace("mesh wi-fi 7 ", "").replace("mesh ", "").replace("combo box wi-fi mesh ", "").replace(" ", "")
    lookup = next((value for label, value in _MESH_DETAILS.items() if label.replace(" ", "") in key), ("Wi-Fi mesh", "Mesh node", None))
    standard, description, badge = lookup
    return OrderProduct(
        code="MESH-" + _slug(name).removeprefix("MESH-"), action="mesh", name=name, description=description,
        monthly_price_myr=price, features=(standard, "Pairs with the home router", "Installed by a technician"), badge=badge,
    )


def _plan_product(name: str, price: float) -> OrderProduct:
    speed = _speed(name)
    tier = next((tier for tier in _TIER_FEATURES if tier in name), None)
    features = [f"{speed // 1000} Gbps fibre" if speed and speed >= 1000 else f"{speed} Mbps fibre" if speed else "Fibre broadband"]
    if tier:
        features.append(_TIER_FEATURES[tier])
    if "Solar Camera" in name:
        features.append("Solar camera included")
    return OrderProduct(
        code=f"PLAN-{_slug(name)}", action="speed", name=name, description=", ".join(features) + ".",
        monthly_price_myr=price, speed_mbps=speed, tier=tier, features=tuple(features),
    )


def load_catalog(path: Path = PRODUCT_CSV) -> dict[str, OrderProduct]:
    """Plans and mesh hardware from product.csv, plus the free reboot work order."""
    products: list[OrderProduct] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("plan_name") or "").strip()
            try:
                price = float(row.get("price_per_month") or "")
            except ValueError:
                continue
            if not name:
                continue
            products.append(_mesh_product(name, price) if "mesh" in name.lower() else _plan_product(name, price))
    for product in list(products):
        if product.action == "mesh" and "combo box" in product.name.lower():
            products.append(OrderProduct(
                code=product.code.replace("MESH-", "RTR-", 1), action="replace", name=f"{product.name} (replacement router)",
                description=f"{product.description}; replaces the faulty home router.", monthly_price_myr=product.monthly_price_myr,
                features=("Router and mesh in one box", product.features[0] if product.features else "Wi-Fi 6", "Old router collected"),
                badge="Recommended" if "2.5G" not in product.name else None,
            ))
    products.append(OrderProduct(
        "WO-REBOOT", "reboot", "Remote router reboot work order",
        "Schedule a remote reboot and a follow-up health check.", one_time_price_myr=0.0,
        features=("No charge", "Follow-up health check"),
    ))
    return {product.code: product for product in products}


CATALOG: dict[str, OrderProduct] = load_catalog()


def plan_price(plan_name: str | None) -> float | None:
    if not plan_name:
        return None
    product = CATALOG.get(f"PLAN-{_slug(plan_name)}")
    return product.monthly_price_myr if product else None


class OrderValidationError(ValueError):
    pass


@dataclass(frozen=True)
class OrderOption:
    action: str
    label: str
    recommended: bool
    products: list[OrderProduct]


@dataclass(frozen=True)
class OrderRecord:
    order: ServiceOrder
    email_status: str
    email_recipient: str | None
    email_error: str | None


def current_plan_speed(plan_name: str | None) -> int | None:
    return _speed(plan_name) if plan_name else None


def _speed_upgrades(plan_name: str | None) -> list[OrderProduct]:
    """Faster plans, same Home Shield tier first, then cheapest first."""
    speed = current_plan_speed(plan_name)
    tier = next((tier for tier in _TIER_FEATURES if plan_name and tier in plan_name), None)
    camera = bool(plan_name and "Solar Camera" in plan_name)
    plans = [product for product in CATALOG.values() if product.action == "speed"
             and (speed is None or (product.speed_mbps or 0) > speed)]
    plans.sort(key=lambda product: (product.tier != tier, ("Solar Camera" in product.name) != camera,
                                    product.speed_mbps or 0, product.monthly_price_myr or 0))
    upgrades = plans[:6]
    if upgrades:
        first = upgrades[0]
        upgrades[0] = OrderProduct(**{**first.__dict__, "badge": "Recommended"})
    return upgrades


def order_options(actions: list[str], plan_name: str | None) -> list[OrderOption]:
    """Recommended actions first, each with the products that satisfy it."""
    mesh = sorted((product for product in CATALOG.values() if product.action == "mesh"),
                  key=lambda product: product.monthly_price_myr or 0)
    products = {
        "mesh": mesh,
        "speed": _speed_upgrades(plan_name),
        "reboot": [product for product in CATALOG.values() if product.action == "reboot"],
        "replace": [product for product in CATALOG.values() if product.action == "replace"],
    }
    # Orderable products first: a mesh node or faster plan before the free reboot work order.
    ordered = sorted((action for action in dict.fromkeys(actions) if action in ORDER_ACTIONS), key=ORDER_ACTIONS.index)
    options = [
        OrderOption(action=action, label=ACTION_LABELS[action], recommended=True, products=products[action])
        for action in ordered
        if products[action] and action != "replace"
    ]
    # summarize.py escalates a reboot to "replace the router if the problem continues".
    if "reboot" in ordered and products["replace"]:
        options.append(OrderOption(action="replace", label=ACTION_LABELS["replace"], recommended=False, products=products["replace"]))
    return options


def submit_order(
    session: Session,
    ticket_id: str,
    actor: AuthenticatedUser,
    *,
    action: str,
    product_code: str,
    notes: str | None,
    settings: Settings,
) -> OrderRecord:
    detail = ticket_queries.get_ticket_detail(session, ticket_id, actor)
    if action not in ORDER_ACTIONS:
        raise OrderValidationError("Unsupported order action")
    product = CATALOG.get(product_code)
    if product is None or product.action != action:
        raise OrderValidationError("The product does not match the selected action")
    order = ServiceOrder(
        ticket_id=detail.ticket.id,
        customer_id=detail.customer.id,
        actor_id=actor.id,
        action=action,
        product_code=product.code,
        product_name=product.name,
        monthly_price_myr=product.monthly_price_myr,
        one_time_price_myr=product.one_time_price_myr,
        notes=(notes or "").strip()[:500] or None,
        status="submitted",
        email_status="pending",
    )
    session.add(order)
    session.flush()

    status, recipient, error = send_order_email(settings, order, detail.customer, actor, login_id=detail.ticket.login_id)
    order.email_status = status
    order.email_recipient = recipient
    order.email_error = error
    session.add(
        AuditEvent(
            actor_id=actor.id,
            ticket_id=detail.ticket.id,
            event_type="order_submitted",
            details={
                "order_id": order.id,
                "action": action,
                "product_code": product.code,
                "email_status": status,
            },
        )
    )
    session.commit()
    return OrderRecord(order=order, email_status=status, email_recipient=recipient, email_error=error)


def list_orders(session: Session, ticket_id: str, actor: AuthenticatedUser) -> list[ServiceOrder]:
    ticket_queries.get_ticket_detail(session, ticket_id, actor)
    return list(
        session.scalars(
            select(ServiceOrder).where(ServiceOrder.ticket_id == ticket_id).order_by(ServiceOrder.created_at.desc())
        ).all()
    )


def send_order_email(
    settings: Settings,
    order: ServiceOrder,
    customer: Customer,
    actor: AuthenticatedUser,
    *,
    login_id: str | None = None,
) -> tuple[str, str | None, str | None]:
    """Return (status, recipient, error). Status is sent, skipped, or failed."""
    recipient = customer.email_address if settings.order_email_to_customer else settings.order_email_to
    if not settings.smtp_username or not settings.smtp_password:
        return "skipped", recipient, "SMTP_USERNAME and SMTP_PASSWORD are not configured"
    if not recipient:
        return "skipped", None, "No order e-mail recipient is configured (ORDER_EMAIL_TO)"

    message = EmailMessage()
    message["Subject"] = f"Order confirmation: {order.product_name}"
    message["From"] = settings.order_email_from or settings.smtp_username
    message["To"] = recipient
    login = _unifi_login(login_id or customer.customer_ref)
    message.set_content(_email_body(order, customer, login))
    message.add_alternative(_email_html(order, customer, login), subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        return "failed", recipient, str(error)[:400]
    return "sent", recipient, None


def _unifi_login(login: str | None) -> str:
    if not login:
        return "-"
    return login if "@" in login else f"{login}@unifi"


def _price(order: ServiceOrder) -> str:
    if order.monthly_price_myr is not None:
        return f"RM {order.monthly_price_myr:.2f} / month"
    return f"RM {order.one_time_price_myr or 0:.2f} one-time"


def _email_fields(order: ServiceOrder, customer: Customer) -> list[tuple[str, str]]:
    fields = [
        ("Product", order.product_name),
        ("Account", customer.account_no or customer.customer_ref or "-"),
        ("Address", customer.address or "-"),
    ]
    if order.notes:
        fields.append(("Notes", order.notes))
    fields.append(("Price", _price(order)))
    return fields


def _email_body(order: ServiceOrder, customer: Customer, login: str) -> str:
    lines = [f"Please confirm with customer for this order: {login}", ""]
    lines += [f"{label}: {value}" for label, value in _email_fields(order, customer)]
    return "\n".join(lines)


def _email_html(order: ServiceOrder, customer: Customer, login: str) -> str:
    """Table layout with inline styles: the only form Gmail and Outlook render consistently."""
    esc = html.escape
    rows = "".join(
        f'<tr><td style="padding:14px 0;border-top:1px solid #eef2f6;color:#64748b;font-size:13px;width:96px;vertical-align:top;">{esc(label)}</td>'
        f'<td style="padding:14px 0;border-top:1px solid #eef2f6;color:#0f172a;font-size:14px;line-height:1.5;'
        f'{"font-weight:700;font-size:16px;color:#003da5;" if label == "Price" else ""}">{esc(str(value))}</td></tr>'
        for label, value in _email_fields(order, customer)
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 12px;"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:16px;">
  <tr><td style="height:4px;background:#003da5;border-radius:16px 16px 0 0;font-size:0;line-height:0;">&nbsp;</td></tr>
  <tr><td style="padding:28px 28px 8px;">
    <p style="margin:0 0 6px;color:#f37021;font-size:12px;font-weight:700;letter-spacing:.04em;">ACTION NEEDED</p>
    <p style="margin:0;color:#0f172a;font-size:18px;line-height:1.45;font-weight:600;">Please confirm with customer for this order:</p>
    <p style="margin:6px 0 0;color:#003da5;font-size:18px;font-weight:700;">{esc(login)}</p>
  </td></tr>
  <tr><td style="padding:16px 28px 28px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>
</table>
</td></tr></table>
</body></html>"""
