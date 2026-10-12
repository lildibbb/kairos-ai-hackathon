"""Chat completion providers selected by ``MODEL_PROVIDER``.

The local provider is deterministic and key-free so the answer path can run in
tests and offline. A hosted OpenAI-compatible provider can replace it.
"""

import json
import re
from collections.abc import Iterator, Sequence

import httpx

from app.ai.ports import ChatCompletionProvider, ChatMessage
from app.config import Settings
from app.integrations.http import post_json, verify_setting


class LocalDeterministicChatProvider:
    """Key-free provider used for local runs and tests.

    When the caller supplies retrieved evidence, it returns a valid structured
    assistant answer grounded only in those chunks, so the grounded path and its
    citation validation run without an external model. Without evidence it falls
    back to a deterministic echo rather than pretending to reason.
    """

    def complete(self, messages: Sequence[ChatMessage], *, temperature: float = 0.0) -> str:
        if messages and "planning a safe remote remediation" in messages[0].content:
            return _local_plan(messages)
        if messages and "Choose a tool from this allowlist" in messages[0].content:
            return _local_tool_call(messages)
        evidence = _extract_retrieved_chunks(messages)
        if evidence is not None:
            return _synthesize_grounded_answer(evidence)
        last_user = next((message.content for message in reversed(messages) if message.role == "user"), "")
        return json.dumps(
            {"provider": "local-deterministic", "prompt_excerpt": last_user[:200]},
            separators=(",", ":"),
        )


class HostedChatCompletionProvider:
    """OpenAI-compatible ``/chat/completions`` calls for a configured provider."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
        verify: bool | str = True,
        timeout_seconds: float = 60.0,
        max_output_tokens: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith("https://") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise ValueError("Hosted model API must use HTTPS")
        self.api_key = api_key
        self.model = model
        self.verify = verify
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self._client = client

    def complete(self, messages: Sequence[ChatMessage], *, temperature: float = 0.0) -> str:
        if not self.api_key or self.api_key.startswith("LOCAL_ONLY"):
            raise RuntimeError("MODEL_PROVIDER=hosted requires a configured MODEL_API_KEY")
        client = self._client or httpx.Client(timeout=self.timeout_seconds, verify=self.verify)
        try:
            payload = {
                "model": self.model,
                "temperature": temperature,
                "messages": [{"role": message.role, "content": message.content} for message in messages],
            }
            if self.max_output_tokens is not None:
                payload["max_tokens"] = self.max_output_tokens
            response = post_json(
                client,
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                payload=payload,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("Chat provider returned an empty or unsupported message content")
            return content
        finally:
            if self._client is None:
                client.close()


def build_chat_provider(
    settings: Settings,
    *,
    purpose: str = "chat",
    timeout_seconds: float = 60.0,
    max_output_tokens: int | None = None,
) -> ChatCompletionProvider:
    provider = (settings.reasoning_provider if purpose == "reasoning" else settings.model_provider).strip().lower()
    if provider in ("", "local", "deterministic"):
        return LocalDeterministicChatProvider()
    if provider == "hosted":
        if not settings.model_api_key or settings.model_api_key.startswith("LOCAL_ONLY"):
            raise RuntimeError("Hosted model providers require MODEL_API_KEY")
        return HostedChatCompletionProvider(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model=settings.reasoning_model_name if purpose == "reasoning" else settings.model_name,
            verify=verify_setting(settings),
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
    raise ValueError(f"Unknown provider for {purpose}: {provider}")


def _extract_retrieved_chunks(messages: Sequence[ChatMessage]) -> list[dict] | None:
    for message in reversed(messages):
        if message.role != "user":
            continue
        outermost = _outermost_object(message.content)
        if outermost is not None:
            chunks = _chunks_from(outermost)
            if chunks is not None:
                return chunks
        for candidate in _iter_json_objects(message.content):
            chunks = _chunks_from(candidate)
            if chunks is not None:
                return chunks
    return None


def _chunks_from(text: str) -> list[dict] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    chunks = parsed.get("chunks") if isinstance(parsed, dict) else None
    if isinstance(chunks, list):
        return [chunk for chunk in chunks if isinstance(chunk, dict)]
    return None


def _outermost_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _synthesize_grounded_answer(chunks: Sequence[dict]) -> str:
    usable = [
        chunk
        for chunk in chunks
        if isinstance(chunk.get("chunk_id"), str)
        and isinstance(chunk.get("content"), str)
        and chunk["content"].strip()
    ]
    if not usable:
        return json.dumps(
            {
                "answer": "No retrieved evidence was usable for this question.",
                "citations": [],
                "uncertainty": "",
                "next_best_action": None,
            },
            separators=(",", ":"),
        )

    primary = usable[0]
    citations = [
        {
            "chunk_id": chunk["chunk_id"],
            "document_title": str(chunk.get("document_title", "")),
            "section": str(chunk.get("section", "")),
        }
        for chunk in usable[:2]
    ]
    first_step = _first_sentence(primary["content"])
    title = str(primary.get("document_title", "the retrieved procedure"))
    answer = (
        f"Retrieved procedural evidence from {title} states: {first_step} "
        "Treat this as a recommendation from the cited procedure and confirm against the observed "
        "ticket data on site."
    )
    dispatch_required = any(
        keyword in primary["content"].lower() for keyword in ("escalate", "dispatch", "site visit")
    )
    next_best_action = {
        "remediation": first_step,
        "dispatch_required": dispatch_required,
        "suggestion": None,
        "evidence": [primary["chunk_id"]],
        "suggestion_evidence": [],
    }
    return json.dumps(
        {
            "answer": answer,
            "citations": citations,
            "uncertainty": "Deterministic local provider; confirm against the cited section.",
            "next_best_action": next_best_action,
        },
        separators=(",", ":"),
    )


_CHANNEL_RE = re.compile(r"channel[^0-9]{0,12}(\d{1,3})", re.IGNORECASE)
_CHANNEL_FALLBACK_RE = re.compile(r"(?:to|set|use|move|change)[^0-9]{0,12}(\d{1,3})", re.IGNORECASE)


def _request_fields(messages: Sequence[ChatMessage]) -> tuple[str, str, dict, dict]:
    """Return the question, device_id, allowlist, and evidence from a tool prompt."""
    request = next((message.content for message in reversed(messages) if message.role == "user"), "")
    data = _first_json_object(request)
    if not isinstance(data, dict):
        return request, "", {}, {}
    question = str(data.get("question", ""))
    device_id = str(data.get("device_id", ""))
    allowlist = {
        item.get("name"): item
        for item in data.get("allowlist", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    evidence = data.get("retrieved_evidence")
    return question, device_id, allowlist, evidence if isinstance(evidence, list) else []


def _channel_request(question: str) -> dict | None:
    """Parse a requested Wi-Fi channel and infer its band from the question."""
    lowered = question.lower()
    match = _CHANNEL_RE.search(lowered) or _CHANNEL_FALLBACK_RE.search(lowered)
    if match is None:
        return None
    channel = int(match.group(1))
    if not 1 <= channel <= 165:
        return None
    band = "5" if channel > 13 else "2.4"
    return {"band": band, "channel": channel}


def _local_tool_call(messages: Sequence[ChatMessage]) -> str:
    question, device_id, _, _ = _request_fields(messages)
    lowered = question.lower()
    channel = _channel_request(question)
    if channel is not None:
        arguments: dict[str, object] = {"device_id": device_id, **channel}
        return json.dumps(
            {"tool_name": "set_wifi_channel", "arguments": arguments}, separators=(",", ":")
        )
    if "ssid" in lowered or "rename" in lowered:
        return json.dumps(
            {"tool_name": "set_wifi_ssid", "arguments": {"device_id": device_id, "ssid_5g": "Home_5G"}},
            separators=(",", ":"),
        )
    if "reboot" in lowered:
        tool_name = "reboot_router"
    elif "config" in lowered:
        tool_name = "update_config"
    else:
        tool_name = "get_device_status"
    arguments = {"device_id": device_id}
    if tool_name == "update_config":
        arguments["settings"] = {"wifi_channel": 6}
    return json.dumps({"tool_name": tool_name, "arguments": arguments}, separators=(",", ":"))


_PLAN_PARAMS: dict[str, dict] = {
    "update_config": {"settings": {"wifi_channel": 6}},
    "set_wifi_channel": {"band": "2.4", "channel": 6},
    "set_wifi_ssid": {"ssid_5g": "Home_5G"},
    "block_client": {"client_mac": "a4:83:e7:11:22:04"},
    "set_dhcp_reservation": {"client_mac": "a4:83:e7:11:22:04", "ip_address": "192.168.0.40"},
}

_PLAN_KEYWORDS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("ssid", "rename", "network name"), ("set_wifi_ssid", "update_config")),
    (("channel", "congestion", "interference", "band"), ("set_wifi_channel", "update_config", "run_speed_test")),
    (("config", "configure", "setting"), ("update_config", "set_wifi_channel", "run_speed_test")),
    (("dns", "resolver", "lookup"), ("flush_dns_cache", "get_device_status")),
    (("voice", "vobb", "sip", "dial tone"), ("restart_service", "get_device_status")),
    (("iptv", "stream", "buffer"), ("restart_service", "get_device_status")),
    (("speed", "throughput", "slow", "bandwidth", "download"), ("run_speed_test", "update_config")),
    (("client", "quarantine", "rogue"), ("list_connected_clients", "block_client")),
    (("reboot", "unreachable", "power cycle"), ("reboot_router", "reboot_ont", "get_device_status")),
    (("optical", "los", "pon", "loss", "rx power", "fiber"), ("run_optical_diagnostics", "reboot_ont", "refresh_ont_registration", "reset_optical_port")),
]

# The local planner returns a superset so device-type validation can still find a
# match after candidates that do not apply to the target device are filtered out.
_LOCAL_PLAN_LIMIT = 10


def _local_plan(messages: Sequence[ChatMessage]) -> str:
    question, _, allowlist, evidence = _request_fields(messages)
    lowered = question.lower()
    evidence_hay = " ".join(
        str(chunk.get("content", "")) for chunk in evidence if isinstance(chunk, dict)
    ).lower()
    channel = _channel_request(question)

    order: list[str] = []
    if channel is not None:
        order.append("set_wifi_channel")
    # The technician's request outranks incidental keywords in the retrieved text.
    for keywords, tools in _PLAN_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            order.extend(tools)
    for keywords, tools in _PLAN_KEYWORDS:
        if any(keyword in evidence_hay for keyword in keywords):
            order.extend(tools)
    order.extend(["get_device_status", "list_connected_clients"])

    suggestions: list[dict] = []
    seen: set[str] = set()
    for name in order:
        if name in seen or name not in allowlist:
            continue
        parameters = dict(_PLAN_PARAMS.get(name, {}))
        if name == "set_wifi_channel" and channel is not None:
            parameters = dict(channel)
        if name == "update_config" and channel is not None:
            if channel["channel"] > 13:
                continue
            parameters = {"settings": {"wifi_channel": channel["channel"]}}
        if name == "restart_service":
            if "iptv" in lowered or "iptv" in evidence_hay:
                parameters = {"service": "iptv"}
            elif "hsi" in lowered or "speed" in lowered:
                parameters = {"service": "hsi"}
            else:
                parameters = {"service": "vobb"}
        seen.add(name)
        suggestions.append(
            {
                "tool_name": name,
                "rationale": f"{allowlist[name].get('description', name)} matches the observed ticket evidence.",
                "confidence": round(max(0.4, 0.9 - 0.1 * len(suggestions)), 2),
                "parameters": parameters,
            }
        )
        if len(suggestions) >= _LOCAL_PLAN_LIMIT:
            break

    return json.dumps(
        {
            "summary": "Deterministic local plan ranked from the retrieved procedure and ticket evidence.",
            "suggestions": suggestions,
        },
        separators=(",", ":"),
    )


def _first_json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _first_sentence(text: str) -> str:
    stripped = text.strip()
    for index, character in enumerate(stripped):
        if character in ".!?" and index + 1 < len(stripped):
            return stripped[: index + 1].strip()
    return stripped


def _iter_json_objects(text: str) -> Iterator[str]:
    depth = 0
    start: int | None = None
    for index, character in enumerate(text):
        if character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None
