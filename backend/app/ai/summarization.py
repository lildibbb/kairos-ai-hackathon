"""Adapts the standalone ``app/summarize.py`` logic to in-app AI reasoning.

The summarizer module owns its own database connection and prompt contract, so
this adapter never reimplements any of it. It feeds the unchanged
``customer_facts`` / ``parse_reply`` / action-guardrail functions the same tuple
shapes they expect from PostgreSQL, and adds the retrieved knowledge chunks as
read-only evidence. The import is lazy so the API keeps working when the
summarizer's optional HTTP dependencies are not installed.
"""

from __future__ import annotations

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
) -> ReasonedSummary:
    """Summarize ticket facts plus retrieved KB evidence through summarize.py."""
    summarizer = _summarizer()
    facts = build_customer_facts(login_id, devices, routers, plan_name)
    raw = _provider_reply(summarizer, provider, facts, matches)
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
    """Apply summarize.py's parsing and deterministic action rules to an answer."""
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
        product_from_actions=False,
        product_recommendation=product_recommendation,
    )


def _provider_reply(
    summarizer: Any,
    provider: ChatCompletionProvider,
    facts: str,
    matches: list[ChunkMatch],
) -> str:
    evidence = "\n\n".join(
        f"[{match.chunk_id}] {match.document_title} / {match.section}: {match.content}"
        for match in matches
    )
    prompt = (
        "Device and router facts:\n\n"
        f"{facts}\n\n"
        "Retrieved knowledge-base evidence:\n\n"
        f"{evidence}\n\n"
        "Write the exact PROBLEM, SUGGESTION, ACTIONS response required above. "
        "Ground every statement in the facts and evidence supplied here."
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
    # labels, so fall back to a grounded reply built only from cited evidence.
    if "PROBLEM:" not in raw.upper():
        raw = _grounded_reply(matches)
    return raw


def _grounded_reply(matches: list[ChunkMatch]) -> str:
    steps = ". ".join(match.content.split(".", 1)[0].strip() for match in matches[:2])
    steps = steps or "No grounded step was retrieved."
    return f"PROBLEM: {steps}.\nSUGGESTION: {steps}.\nACTIONS:"


def _reasoned(
    summarizer: Any,
    facts: str,
    raw: str,
    *,
    product_from_actions: bool,
    product_recommendation: str | None = None,
) -> ReasonedSummary:
    problem, suggestion, actions = summarizer.parse_reply(raw)
    suggestion, actions = summarizer.ensure_coverage_action(suggestion, actions, facts)
    suggestion = summarizer.sentence_case(summarizer.ensure_reboot_escalation(suggestion, facts))
    if product_from_actions:
        product_recommendation = _product_recommendation(actions, suggestion)
    return ReasonedSummary(
        problem=problem,
        solution=suggestion or None,
        product_recommendation=product_recommendation,
        actions=actions,
        facts=facts,
    )


def _product_recommendation(actions: list[str], suggestion: str) -> str | None:
    lower = suggestion.lower()
    if "mesh" in actions and ("mesh" in lower or "repeater" in lower):
        return suggestion
    if "speed" in actions and ("plan" in lower or "speed" in lower):
        return suggestion
    return None


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
