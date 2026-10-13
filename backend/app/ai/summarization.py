"""Adapts the standalone ``app/summarize.py`` logic to in-app AI reasoning.

The summarizer module owns its own database connection and prompt contract, so
this adapter never reimplements any of it. It feeds the unchanged
``customer_facts`` / ``parse_reply`` / action-guardrail functions the same tuple
shapes they expect from PostgreSQL, and adds the retrieved knowledge chunks as
read-only evidence. The import is lazy so the API keeps working when the
summarizer's optional HTTP dependencies are not installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.ai.ports import ChatCompletionProvider, ChatMessage, ChunkMatch


class SummarizerUnavailable(RuntimeError):
    """The unchanged summarize.py module could not be imported."""


@dataclass(frozen=True)
class ReasonedSummary:
    problem: str
    solution: str | None
    product_recommendation: str | None
    actions: list[str]
    facts: str


@lru_cache(maxsize=1)
def _summarizer() -> Any:
    try:
        from app import summarize
    except ImportError as error:  # pragma: no cover - depends on local env
        raise SummarizerUnavailable(str(error)) from error
    return summarize


def build_customer_facts(
    login_id: str,
    devices: list[Any],
    routers: list[Any],
    plan_name: str | None = None,
    plan_price: float | None = None,
) -> str:
    """Render ORM inventory into the unchanged summarizer's tuple contract."""
    summarizer = _summarizer()
    device_rows = [_device_row(device) for device in devices]
    router_row = _router_row(routers[0]) if routers else None
    return summarizer.customer_facts(login_id, device_rows, router_row, plan_name, plan_price)


def summarize_matches(
    *,
    login_id: str,
    devices: list[Any],
    routers: list[Any],
    matches: list[ChunkMatch],
    provider: ChatCompletionProvider,
    plan_name: str | None = None,
    ticket_note: str | None = None,
    plan_price: float | None = None,
) -> ReasonedSummary:
    """Summarize ticket facts plus retrieved KB evidence through summarize.py."""
    summarizer = _summarizer()
    facts = build_customer_facts(login_id, devices, routers, plan_name, plan_price)
    raw = _provider_reply(summarizer, provider, facts, matches, ticket_note)
    return _reasoned(summarizer, facts, raw, product_from_actions=True)


def summarize_answer(
    *,
    login_id: str,
    devices: list[Any],
    routers: list[Any],
    answer: str,
    solution: str | None,
    product_recommendation: str | None,
    actions: list[str] | None = None,
    plan_name: str | None = None,
) -> ReasonedSummary:
    """Apply summarize.py's parsing and deterministic action rules to an answer.

    The chat model's remediation text is only a candidate SUGGESTION: a "no
    remediation found" sentence is dropped so the facts-driven guardrails
    (reboot, mesh, plan, replace) decide the proposed solution instead.
    """
    summarizer = _summarizer()
    facts = build_customer_facts(login_id, devices, routers, plan_name)
    raw = "\n".join(
        (
            f"PROBLEM: {answer}",
            f"SUGGESTION: {solution or ''}",
            f"ACTIONS: {','.join(actions or [])}",
        )
    )
    return _reasoned(
        summarizer,
        facts,
        raw,
        product_from_actions=not product_recommendation,
        product_recommendation=product_recommendation,
    )


def _provider_reply(
    summarizer: Any,
    provider: ChatCompletionProvider,
    facts: str,
    matches: list[ChunkMatch],
    ticket_note: str | None = None,
) -> str:
    evidence = "\n\n".join(
        f"[{match.chunk_id}] {match.document_title} / {match.section}: {match.content}"
        for match in matches
    ) or "No knowledge-base section matched; rely on the facts."
    alarm = f"Ticket alarm: {ticket_note}\n\n" if ticket_note else ""
    prompt = (
        f"{alarm}"
        "Device and router facts:\n\n"
        f"{facts}\n\n"
        "Retrieved knowledge-base evidence:\n\n"
        f"{evidence}\n\n"
        "Write the exact PROBLEM, SUGGESTION, ACTIONS response required above. "
        "The facts are the primary evidence; every 'Recommended action' line in the facts "
        "must appear in SUGGESTION. Use the knowledge-base evidence to explain each step."
    )
    try:
        raw = provider.complete(
            [
                ChatMessage(role="system", content=summarizer.CUSTOMER_SYSTEM),
                ChatMessage(role="user", content=prompt),
            ]
        )
    except Exception:
        raw = ""
    # The local deterministic provider echoes context rather than the required
    # labels, so fall back to a reply built only from the summarize.py facts.
    if "PROBLEM:" not in raw.upper():
        raw = facts_reply(facts, ticket_note)
    return raw


def facts_reply(facts: str, ticket_note: str | None = None) -> str:
    """Deterministic PROBLEM line from summarize.py facts; guardrails add the actions."""
    problems: list[str] = []
    if ticket_note:
        problems.append(f"Ticket alarm: {ticket_note.rstrip('.')}.")
    cpu = re.search(r"Router CPU: (\d+)% \(high\)", facts)
    if cpu:
        problems.append(f"The router CPU usage is high at {cpu.group(1)}%, so the router is working too hard.")
    temp = re.search(r"CPU temperature: (\d+) C \(high\)", facts)
    if temp:
        problems.append(f"The router CPU temperature is high at {temp.group(1)} C.")
    memory = re.search(r"Router memory used: (\d+)%", facts)
    if memory and int(memory.group(1)) >= 80:
        problems.append(f"The router memory use is high at {memory.group(1)}%.")
    weak = re.search(r"- (\d+ of \d+ wireless devices have a weak WiFi signal \(worst -?\d+ dBm\))", facts)
    if weak:
        problems.append(f"{weak.group(1)[0].upper()}{weak.group(1)[1:]}, so the WiFi does not reach every room.")
    if "outdated model, replacement recommended" in facts:
        problems.append("The router is an outdated model.")
    optical = re.search(r"Optical RX power: (-?[\d.]+) dBm \(weak\)", facts)
    if optical:
        problems.append(f"The optical RX power is weak at {optical.group(1)} dBm.")
    usage = re.search(r"Monthly usage is ([\d.]+) GB with (\d+) end devices", facts)
    if usage:
        problems.append(f"Monthly usage is {usage.group(1)} GB across {usage.group(2)} devices, which is too much for the current plan.")
    if not problems:
        problems.append("No significant problem is visible in the device and router facts.")
    return f"PROBLEM: {' '.join(problems)}\nSUGGESTION:\nACTIONS:"


# A chat model sometimes reports that the knowledge base lacked a procedure.
# That is not a solution, so it never reaches the proposed solution.
_NO_REMEDIATION = re.compile(
    r"\b(no|not any|could not find|cannot find|did not find|unable to find)\b[^.]{0,80}"
    r"\b(remediation|solution|steps?|procedure|guidance|fix)\b[^.]{0,80}"
    r"(found|available|provided|evidence|retrieved)|"
    r"\bnot (found|available|covered) in the (provided |retrieved )?(evidence|knowledge)",
    re.I,
)


def strip_unsupported(text: str | None) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(part for part in parts if part.strip() and not _NO_REMEDIATION.search(part)).strip()


def _reasoned(
    summarizer: Any,
    facts: str,
    raw: str,
    *,
    product_from_actions: bool,
    product_recommendation: str | None = None,
) -> ReasonedSummary:
    problem, suggestion, _ = summarizer.parse_reply(raw)
    suggestion = strip_unsupported(suggestion)
    # Re-derive actions from the kept text so a dropped sentence such as
    # "No steps found for CPE_REBOOT_LOOP" cannot imply a reboot order.
    actions = summarizer.sync_actions(suggestion, _declared_actions(summarizer, raw))
    suggestion = summarizer.enforce_required_actions(suggestion, facts)
    suggestion, actions = summarizer.ensure_coverage_action(suggestion, actions, facts)
    suggestion = summarizer.sentence_case(summarizer.ensure_reboot_escalation(suggestion, facts))
    actions = summarizer.sync_actions(suggestion, actions)
    if product_from_actions:
        product_recommendation = product_recommendation_text(actions, facts)
    return ReasonedSummary(
        problem=strip_unsupported(problem) or problem,
        solution=suggestion or None,
        product_recommendation=product_recommendation,
        actions=actions,
        facts=facts,
    )


def _declared_actions(summarizer: Any, raw: str) -> list[str]:
    match = re.search(r"ACTIONS:[ \t]*([^\n]*)", raw, re.I)
    words = re.split(r"[,;/\s]+", match.group(1).lower()) if match else []
    return [key for key in summarizer.ALLOWED_ACTIONS if key in words]


def product_recommendation_text(actions: list[str], facts: str) -> str | None:
    """Plain-language upsell built from the order actions summarize.py selected."""
    offers: list[str] = []
    if "mesh" in actions:
        weak = re.search(r"(\d+ of \d+) wireless devices have a weak WiFi signal", facts)
        reason = f" because {weak.group(1)} wireless devices have a weak WiFi signal" if weak else ""
        offers.append(f"Mesh WiFi node to extend coverage{reason}.")
    if "speed" in actions:
        plan = re.search(r"Current WiFi plan: ([^(\n]+)", facts)
        current = f" from {plan.group(1).strip()}" if plan else ""
        offers.append(f"Upgrade the internet plan{current} to a higher-speed plan for the household's usage.")
    if "outdated model, replacement recommended" in facts:
        offers.append("Replacement router (current AX3000 or BE7200 model).")
    return " ".join(offers) or None


def _device_row(device: Any) -> tuple:
    return (
        device.login_id or "",
        device.device_type,
        device.link_type,
        device.manufacturer,
        device.brand,
        device.friendly_name or device.name,
        device.rssi,
        device.rx_rate,
        device.tx_rate,
        device.platform,
        device.cloud_device_type,
    )


def _router_row(router: Any) -> tuple:
    return (
        router.login_id,
        router.serial_number,
        router.manufacturer,
        router.model,
        router.cpu_usage_pct,
        router.cpu_temperature_c,
        router.memory_usage_pct,
        router.monthly_usage_gb,
        router.rx_power_dbm,
    )
