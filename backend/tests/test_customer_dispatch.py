from sqlalchemy import func, select
from fastapi.testclient import TestClient
import pytest

from app.auth.tokens import create_access_token
from app.config import get_settings
from app.db.session import get_session
from app.domain.models import AuditEvent, CustomerAccount, CustomerChatTurn, CustomerDispatchArea, CustomerTroubleTicket, DispatchArea, Role, TechnicianDispatchArea, User
from app.main import app
from app.seed.customer_dispatch import seed_dispatch
from test_customer_chat import workspace, ask, RecordingChat


def prepare(workspace):
    session, settings, _, actors = workspace
    seed_dispatch(session, settings.model_copy(update={"demo_seed_enabled": True}))
    return session, actors


def fail_checks(workspace, message="Slow internet on every device using Ethernet cable, I want to make a report."):
    first = ask(workspace, message)
    assert first.follow_up.id == "self_help"
    return ask(workspace, "Still not working", conversation_id=first.conversation_id, answer_choice="still_not_working")


def test_failed_checks_auto_assign_to_customer_area_and_audit(workspace):
    session, actors = prepare(workspace)
    result = fail_checks(workspace)
    assert result.status == "report_created" and result.report.status == "assigned"
    assert result.report.reference.startswith("DEMO-TT-") and result.follow_up is None
    ticket = session.scalar(select(CustomerTroubleTicket))
    mapping = session.get(CustomerDispatchArea, session.get(CustomerAccount, actors[0].id).customer_id)
    assert ticket.area_id == mapping.area_id
    assert session.get(TechnicianDispatchArea, (ticket.assigned_technician_id, mapping.area_id))
    assert session.scalar(select(AuditEvent).where(AuditEvent.event_type == "customer_report_created"))
    assert "confirmed an appointment" not in result.answer
    assert "demo" not in result.answer.lower() and "prototype" not in result.answer.lower()
    assert "An appointment has not yet been confirmed" in result.answer
    assert "still present after the troubleshooting checks" in result.answer
    assert "further investigation by a technician" in result.answer
    assert "Your trouble ticket has been created" in result.answer
    assert "fibre" not in result.answer


def test_stale_weak_wifi_never_dispatches_and_coverage_advice_is_conditional(workspace):
    session, _ = prepare(workspace)
    first = ask(workspace, "My internet is slow, I want to make a report.")
    assert first.report is None
    ask(workspace, "Every device", conversation_id=first.conversation_id, answer_choice="all_devices")
    ask(workspace, "Wi-Fi", conversation_id=first.conversation_id, answer_choice="wifi")
    result = ask(workspace, "It improves", conversation_id=first.conversation_id, answer_choice="better_near_router")
    assert "mesh" in result.answer and "may help" in result.answer
    assert "all devices have weak signal" not in result.answer
    assert result.report is None and result.status == "self_help"
    resolved = ask(workspace, "It's working now", conversation_id=first.conversation_id, answer_choice="resolved")
    assert resolved.status == "resolved" and resolved.follow_up is None
    assert session.scalar(select(func.count()).select_from(CustomerTroubleTicket)) == 0


def test_red_los_report_does_not_request_customer_to_reset_fibre(workspace):
    prepare(workspace)
    first = ask(workspace, "No internet on every device using Ethernet, I want to make a report.")
    assert first.follow_up.id == "router_lights"
    result = ask(workspace, "LOS is red", conversation_id=first.conversation_id, answer_choice="red_los")
    assert result.report.status == "assigned"
    assert result.workflow.escalation_reason == "customer_reported_red_los"
    assert result.answer.startswith("The red or blinking LOS light you reported suggests a possible fibre connection issue")
    assert "on-site technician check" in result.answer
    assert result.answer.index("technician check") < result.answer.index("Your trouble ticket")


def test_permission_needed_when_customer_did_not_request_report(workspace):
    prepare(workspace)
    result = fail_checks(workspace, "Slow internet on every device using Ethernet")
    assert result.report is None and result.follow_up.id == "submit_report"
    assert "further investigation by a technician" in result.answer
    assert "I can create a trouble ticket" in result.answer
    assert "has been created" not in result.answer
    submitted = ask(workspace, "Arrange technician review", conversation_id=result.conversation_id, answer_choice="submit_report")
    assert submitted.report.status == "assigned"


def test_negated_request_does_not_auto_create_report(workspace):
    prepare(workspace)
    result = fail_checks(workspace, "Slow internet on every device using Ethernet, don't make a report.")
    assert result.report is None and result.follow_up.id == "submit_report"


@pytest.mark.parametrize("missing_area", [False, True])
def test_missing_area_or_unavailable_technician_queues_honestly(workspace, missing_area):
    session, actors = prepare(workspace)
    mapping = session.get(CustomerDispatchArea, session.get(CustomerAccount, actors[0].id).customer_id)
    if missing_area:
        session.delete(mapping)
    else:
        technicians = session.scalars(select(TechnicianDispatchArea).where(TechnicianDispatchArea.area_id == mapping.area_id))
        for technician in technicians:
            technician.is_available = False
    session.commit()
    result = fail_checks(workspace)
    assert result.report.status == "queued" and "queued for assignment" in result.answer
    assert "further investigation by a technician" in result.answer
    assert "An appointment has not yet been confirmed" in result.answer
    assert session.scalar(select(CustomerTroubleTicket)).assigned_technician_id is None


def test_synthetic_los_reading_does_not_automatically_dispatch(workspace):
    session, actors = prepare(workspace)
    session.get(CustomerAccount, actors[0].id).customer_id = workspace[2]["tables"]["customers"][4]["id"]
    session.commit()
    result = ask(workspace, "No internet on every device using Ethernet, I want to make a report.")
    assert any(f.code == "optical_loss" for f in result.findings)
    assert result.report is None and result.follow_up.id == "router_lights"


def test_duplicate_active_issue_across_conversations_reuses_report(workspace):
    session, _ = prepare(workspace)
    first = fail_checks(workspace)
    second = fail_checks(workspace)
    assert first.report.reference == second.report.reference
    assert session.scalar(select(func.count()).select_from(CustomerTroubleTicket)) == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == "customer_report_created")) == 1


def test_technician_from_other_area_never_assigned(workspace):
    session, actors = prepare(workspace)
    mapping = session.get(CustomerDispatchArea, session.get(CustomerAccount, actors[0].id).customer_id)
    west = session.get(DispatchArea, mapping.area_id)
    east = session.scalar(select(DispatchArea).where(DispatchArea.code == "DEMO-EAST"))
    mapping.area_id = east.id
    session.commit()
    result = fail_checks(workspace)
    ticket = session.scalar(select(CustomerTroubleTicket))
    assert result.report.status == "assigned" and ticket.area_id != west.id
    assert session.get(User, ticket.assigned_technician_id).email == "technician.east@demo.invalid"


def test_seed_is_insert_only_and_preserves_existing_mapping(workspace):
    session, actors = prepare(workspace)
    link = session.get(CustomerAccount, actors[0].id)
    mapping = session.get(CustomerDispatchArea, link.customer_id)
    east = session.scalar(select(DispatchArea).where(DispatchArea.code == "DEMO-EAST"))
    mapping.area_id = east.id
    session.commit()
    settings = workspace[1].model_copy(update={"demo_seed_enabled": True})
    assert seed_dispatch(session, settings)["new_customer_mappings"] == 0
    assert mapping.area_id == east.id


def test_model_cannot_invent_dispatch_eligibility(workspace):
    session, _ = prepare(workspace)
    result = ask(workspace, settings=workspace[1].model_copy(update={"customer_chat_provider": "hosted"}),
        provider=RecordingChat('{"intent":"no_internet","router_lights":"red_los","report_requested":true}'))
    assert result.mode == "fallback" and result.report is None
    assert session.scalar(select(func.count()).select_from(CustomerTroubleTicket)) == 0


def test_checker_only_operator_and_supervisor_and_read_only(workspace):
    session, actors = prepare(workspace)
    result = fail_checks(workspace)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: workspace[1]
    try:
        with TestClient(app) as client:
            for user in (session.get(User, actors[0].id), session.scalar(select(User).join(Role).where(Role.name == "technician"))):
                role = session.get(Role, user.role_id).name
                token, _ = create_access_token(user.id, role)
                assert client.get("/admin/customer-reports", headers={"Authorization": f"Bearer {token}"}).status_code == 403
                assert client.get(f"/admin/customer-reports/{result.conversation_id}", headers={"Authorization": f"Bearer {token}"}).status_code == 403
            operator = session.scalar(select(User).join(Role).where(Role.name == "operator"))
            token, _ = create_access_token(operator.id, "operator")
            headers = {"Authorization": f"Bearer {token}"}
            rows = client.get("/admin/customer-reports", headers=headers)
            assert rows.status_code == 200 and rows.json()[0]["report"]["area"] == "Demo West"
            detail = client.get(f"/admin/customer-reports/{result.conversation_id}", headers=headers)
            assert detail.status_code == 200 and "findings" in detail.json()["turns"][-1]["response"]
            assert client.post("/admin/customer-reports", json={}, headers=headers).status_code == 405
    finally:
        app.dependency_overrides.clear()


def test_customer_receipt_hides_internal_marker_but_keeps_actual_assignment(workspace):
    from app.services.customer_chat import visible_response
    session, _ = prepare(workspace)
    result = fail_checks(workspace)
    customer = visible_response(result).model_dump(mode="json")
    assert customer["report"] == {"ticket_id": result.report.ticket_id, "reference": result.report.reference.removeprefix("DEMO-"), "status": "assigned"}
    assert "is_demo" not in customer and "demo" not in customer["answer"].lower()
    assert session.scalar(select(CustomerTroubleTicket)).is_demo is True
    assert session.scalar(select(CustomerTroubleTicket)).reference == result.report.reference


def test_old_ticket_history_has_normal_customer_copy_without_rewriting_audit_snapshot(workspace):
    from app.services.customer_chat import get_history, visible_response
    session, actors = prepare(workspace)
    result = fail_checks(workspace)
    turn = session.scalar(select(CustomerChatTurn).where(CustomerChatTurn.request_id == result.request_id))
    original = {**turn.response, "answer": f"A local demo trouble ticket is recorded: {result.report.reference}. It has not been sent to live Unifi teams."}
    turn.response = original
    session.commit()
    history = get_history(session, actors[0], result.conversation_id)
    restored = visible_response(history.turns[-1].response)
    assert "demo" not in restored.answer.lower() and "live Unifi" not in restored.answer
    assert "further investigation by a technician" in restored.answer
    assert restored.report.reference.startswith("TT-")
    session.refresh(turn)
    assert turn.response == original


def test_red_los_ticket_reason_is_preserved_in_history_and_retries(workspace):
    from app.services.customer_chat import get_history
    session, actors = prepare(workspace)
    first = ask(workspace, "No internet on every device using Ethernet, I want to make a report.")
    result = ask(workspace, "LOS is red", conversation_id=first.conversation_id, answer_choice="red_los")
    replay = ask(workspace, "LOS is red", conversation_id=first.conversation_id,
        answer_choice="red_los", request_id=result.request_id)
    restored = get_history(session, actors[0], first.conversation_id).turns[-1].response
    assert replay.answer == restored.answer == result.answer
    assert "possible fibre connection issue" in restored.answer
    assert session.scalar(select(func.count()).select_from(CustomerTroubleTicket)) == 1


@pytest.mark.parametrize("reason,explanation", [
    ("verified_optical_los_with_customer_outage", "connection checks indicate a fibre signal problem"),
    (None, "Based on the checks so far, this issue needs technician attention"),
])
def test_receipt_explains_escalation_without_promising_an_appointment(reason, explanation):
    from app.domain.customer_chat_schemas import CustomerReportReceipt
    from app.services.customer_chat import _report_answer
    answer = _report_answer(CustomerReportReceipt(reference="TT-EXAMPLE", status="assigned", is_demo=False), reason)
    assert explanation in answer
    assert "Your trouble ticket has been created: TT-EXAMPLE" in answer
    assert "An appointment has not yet been confirmed" in answer
