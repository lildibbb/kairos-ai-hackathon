from datetime import timedelta

import pytest
from sqlalchemy import select, func

from app.domain.models import CustomerAccount, CustomerChatTurn, CustomerTroubleTicket, DeviceMeasurement, NetworkDevice, ProductOffer, Service, WanUsageSample, WifiClientMeasurement, WifiRadio, WifiRadioMeasurement
from app.seed.customer_dispatch import seed_dispatch
from app.seed.customer_support import seed_support, support_evidence
from app.seed.workforce_data import ingest_support_evidence
from app.services.customer_sales import get_sales_options, official_url
from test_customer_chat import workspace, ask, NOW, RecordingChat


def usage(workspace, *, quality="good", utilization=.95, devices=4, overlap=False):
    session, _, _, actors = workspace
    customer_id = session.get(CustomerAccount, actors[0].id).customer_id
    router = session.scalar(select(NetworkDevice).where(NetworkDevice.customer_id == customer_id, NetworkDevice.device_type == "router"))
    service = session.scalar(select(Service).where(Service.customer_id == customer_id, Service.service_type == "HSI"))
    for index in range(3):
        end = NOW - timedelta(minutes=3 - index if not overlap else 1)
        session.add(WanUsageSample(device_id=router.id, window_start=end - timedelta(minutes=1), window_end=end,
            ingested_at=end + timedelta(seconds=1), download_mbps=service.details["subscribed_download_mbps"] * utilization,
            upload_mbps=1, active_devices=devices, quality=quality, source="test_telemetry"))
    session.commit()


def test_coverage_mesh_information_is_optional_and_does_not_create_ticket(workspace):
    first = ask(workspace, "Slow Wi-Fi on every device")
    response = ask(workspace, "It improves", conversation_id=first.conversation_id, answer_choice="better_near_router")
    assert response.assessment.category == "coverage"
    assert "learn_mesh" in {choice.value for choice in response.follow_up.choices}
    sales = ask(workspace, "Learn about mesh", conversation_id=first.conversation_id, answer_choice="learn_mesh")
    assert sales.status == "sales_options" and sales.report is None
    assert sales.sales_options[0].official_url == "https://unifi.com.my/lifestyle"
    assert sales.sales_options[0].monthly_price_myr is None
    assert "Purchasing is optional" in sales.answer
    assert "request_technician" in {choice.value for choice in sales.follow_up.choices}
    continued = ask(workspace, "Keep troubleshooting", conversation_id=first.conversation_id, answer_choice="keep_troubleshooting")
    assert continued.status == "self_help" and continued.report is None


@pytest.mark.parametrize("scope", ["Every device", "Only one device"])
def test_coverage_message_matches_assessment_for_each_device_scope(workspace, scope):
    first = ask(workspace, "My internet is slow")
    ask(workspace, scope, conversation_id=first.conversation_id,
        answer_choice="all_devices" if scope == "Every device" else "one_device")
    ask(workspace, "Wi-Fi", conversation_id=first.conversation_id, answer_choice="wifi")
    response = ask(workspace, "It improves", conversation_id=first.conversation_id, answer_choice="better_near_router")
    assert response.assessment.category == "coverage"
    assert "weak Wi-Fi coverage at the original location" in response.answer
    assert "may be contributing" in response.answer and "mesh system may help" in response.answer
    assert "equipment purchase is optional" in response.answer
    assert "This may be specific to that device" not in response.answer
    assert "all devices have weak signal" not in response.answer
    assert "learn_mesh" in {choice.value for choice in response.follow_up.choices}
    if scope == "Only one device":
        assert "Compare another device in the same spot" in response.answer
    assert response.report is None


def test_one_device_without_near_router_improvement_keeps_device_checks(workspace):
    first = ask(workspace, "Slow Wi-Fi on only my phone")
    response = ask(workspace, "No improvement", conversation_id=first.conversation_id, answer_choice="same_near_router")
    assert response.assessment.category == "unknown"
    assert "This may be specific to that device" in response.answer
    assert "learn_mesh" not in {choice.value for choice in response.follow_up.choices}


def test_old_inconsistent_coverage_reply_is_formatted_on_history_and_retry_without_rewriting_snapshot(workspace):
    from app.domain.customer_chat_schemas import CustomerChatRequest
    from app.services.customer_chat import get_history

    session, _, _, actors = workspace
    first = ask(workspace, "Slow Wi-Fi on only my phone")
    request = CustomerChatRequest(message="It improves", conversation_id=first.conversation_id, answer_choice="better_near_router")
    response = ask(workspace, request.message, conversation_id=request.conversation_id,
        answer_choice=request.answer_choice, request_id=request.request_id)
    stored = session.scalar(select(CustomerChatTurn).where(CustomerChatTurn.request_id == str(request.request_id)))
    old_answer = "This may be specific to that device. Turn its Wi-Fi off and on, pause large downloads, and compare with another device on the same connection."
    snapshot = {**stored.response, "answer": old_answer}
    stored.response = snapshot
    session.commit()
    history = get_history(session, actors[0], first.conversation_id)
    replay = ask(workspace, request.message, conversation_id=request.conversation_id,
        answer_choice=request.answer_choice, request_id=request.request_id)
    assert history.turns[-1].response.answer == replay.answer == response.answer
    session.refresh(stored)
    assert stored.response == snapshot


def test_capacity_requires_actual_repeated_usage_and_customer_comparison(workspace):
    usage(workspace)
    first = ask(workspace, "Slow internet on every device using Ethernet")
    assert first.follow_up.id == "capacity_check" and first.assessment.sales_categories == []
    response = ask(workspace, "It improves when paused", conversation_id=first.conversation_id, answer_choice="better_when_paused")
    assert response.assessment.category == "bandwidth_capacity"
    assert "compare_plans" in {choice.value for choice in response.follow_up.choices}
    assert "may help" in response.answer and "optional" in response.answer
    sales = ask(workspace, "Compare plans", conversation_id=first.conversation_id, answer_choice="compare_plans")
    assert sales.status == "sales_options" and sales.report is None
    assert sales.sales_options[0].official_url == "https://unifi.com.my/broadband"


@pytest.mark.parametrize("options", [{"utilization": .05, "devices": 25}, {"quality": "simulated"}, {"quality": "stale"}, {"overlap": True}])
def test_count_simulated_stale_or_duplicate_windows_cannot_drive_capacity_sales(workspace, options):
    usage(workspace, **options)
    response = ask(workspace, "Slow internet on every device using Ethernet")
    assert response.assessment.category != "bandwidth_capacity"
    assert response.follow_up.id == "self_help"
    assert "compare_plans" not in {choice.value for choice in response.follow_up.choices}


def test_no_improvement_after_pausing_does_not_promote_upgrade(workspace):
    usage(workspace)
    first = ask(workspace, "Slow internet on every device using Ethernet")
    response = ask(workspace, "No improvement when paused", conversation_id=first.conversation_id, answer_choice="same_when_paused")
    assert response.assessment.category == "unknown" and response.assessment.sales_categories == []


def test_radio_congestion_is_not_a_broadband_sales_trigger(workspace):
    session, _, _, actors = workspace
    customer_id = session.get(CustomerAccount, actors[0].id).customer_id
    router = session.scalar(select(NetworkDevice).where(NetworkDevice.customer_id == customer_id, NetworkDevice.device_type == "router"))
    radio = session.scalar(select(WifiRadio).where(WifiRadio.device_id == router.id))
    client = session.scalar(select(WifiClientMeasurement).join(NetworkDevice, NetworkDevice.id == WifiClientMeasurement.client_device_id).where(NetworkDevice.customer_id == customer_id).order_by(WifiClientMeasurement.observed_at.desc()))
    client.quality = "good"; client.retry_pct = 30
    session.add(WifiRadioMeasurement(radio_id=radio.id, observed_at=NOW, ingested_at=NOW, quality="good", source="test_telemetry", channel_utilization_pct=90))
    session.commit()
    first = ask(workspace, "Slow Wi-Fi on every device")
    response = ask(workspace, "No improvement", conversation_id=first.conversation_id, answer_choice="same_near_router")
    assert response.assessment.category == "radio_congestion"
    assert response.assessment.sales_categories == [] and "radio congestion" in response.answer


def test_profile_mismatch_takes_precedence_over_coverage_sales(workspace):
    session, _, data, actors = workspace
    session.get(CustomerAccount, actors[0].id).customer_id = data["tables"]["customers"][3]["id"]
    session.commit()
    first = ask(workspace, "Slow Wi-Fi on every device")
    response = ask(workspace, "It improves", conversation_id=first.conversation_id, answer_choice="better_near_router")
    assert response.assessment.category == "profile_review" and response.assessment.sales_categories == []
    assert "higher-priced plan is not the first step" in response.answer


def test_customer_can_decline_sales_and_request_visit_without_claiming_fault(workspace):
    session, settings, _, _ = workspace
    seed_dispatch(session, settings.model_copy(update={"demo_seed_enabled": True}))
    first = ask(workspace, "Slow Wi-Fi on every device")
    ask(workspace, "It improves", conversation_id=first.conversation_id, answer_choice="better_near_router")
    ask(workspace, "Learn about mesh", conversation_id=first.conversation_id, answer_choice="learn_mesh")
    visit = ask(workspace, "Request a technician", conversation_id=first.conversation_id, answer_choice="request_technician")
    assert visit.status == "report_created" and visit.report.ticket_id
    assert visit.workflow.escalation_reason == "customer_requested_visit"
    assert "exact cause has not been confirmed" in visit.answer
    assert session.scalar(select(CustomerTroubleTicket)).reason == "customer_requested_visit"


def test_model_cannot_invent_visit_or_sales_action(workspace):
    response = ask(workspace, settings=workspace[1].model_copy(update={"customer_chat_provider": "hosted"}),
        provider=RecordingChat('{"intent":"slow_internet","requested_action":"technician"}'))
    assert response.mode == "fallback" and response.report is None and response.sales_options == []


@pytest.mark.parametrize("url", ["https://unifi.com.my.evil.invalid/", "javascript:alert(1)", "http://unifi.com.my/", "https://user@unifi.com.my/", "https://unifi.com.my:8443/"])
def test_unofficial_urls_are_rejected(url):
    assert not official_url(url)


def test_offers_filter_expiry_eligibility_compatibility_and_unverified_prices(workspace):
    session, settings, _, actors = workspace
    customer_id = session.get(CustomerAccount, actors[0].id).customer_id
    seed_support(session, settings.model_copy(update={"demo_seed_enabled": True}), now=NOW)
    offer = session.scalar(select(ProductOffer).where(ProductOffer.category == "mesh"))
    offer.monthly_price_myr = 99
    session.commit()
    assert get_sales_options(session, customer_id, "mesh", now=NOW)[0].monthly_price_myr is None
    for updates in ({"valid_until": NOW}, {"verified_at": NOW - timedelta(days=8)}, {"eligibility": "new_customer"}, {"compatible_models": ["not-this-router"]}, {"official_url": "https://evil.invalid/"}):
        original = {key: getattr(offer, key) for key in updates}
        for key, value in updates.items(): setattr(offer, key, value)
        session.flush()
        assert get_sales_options(session, customer_id, "mesh", now=NOW)[0].id == "official-mesh"
        for key, value in original.items(): setattr(offer, key, value)
    offer.eligibility = "existing_customer"
    session.flush()
    assert get_sales_options(session, customer_id, "mesh", now=NOW)[0].monthly_price_myr == 99


def test_support_evidence_is_insert_only_and_never_promoted_to_live(workspace):
    session, _, dataset, _ = workspace
    rows = support_evidence(dataset)
    assert ingest_support_evidence(session, rows)["new_support_measurements"] > 0
    assert ingest_support_evidence(session, rows)["new_support_measurements"] == 0
    assert session.scalar(select(func.count()).select_from(WanUsageSample).where(WanUsageSample.quality != "simulated")) == 0
    rows["wan_usage_samples"][0]["quality"] = "good"
    with pytest.raises(ValueError, match="remain marked simulated"):
        ingest_support_evidence(session, rows)
