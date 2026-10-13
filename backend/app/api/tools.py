import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.ai.ports import ChatCompletionProvider, EmbeddingProvider
from app.api.assistant import get_embedding_provider
from app.config import get_settings
from app.integrations.model_provider import build_chat_provider
from app.services.agent_tools import AgentToolProposalError, plan_agent_tools, propose_agent_tool
from app.db.session import get_session
from app.domain.tool_schemas import (
    AgentPlanRead,
    AgentPlanSuggestionRead,
    AgentToolProposeRequest,
    ToolCatalogItemRead,
    ToolConfirmRequest,
    ToolExecutionRead,
    ToolProposalRead,
    ToolProposeRequest,
)
from app.services import tool_execution
from app.services.ticket_queries import TicketNotFoundError
from app.services.tool_execution import (
    ToolForbiddenError,
    ToolNotFoundError,
    ToolValidationError,
)

router = APIRouter(prefix="/tickets", tags=["tools"])


def get_reasoning_provider() -> ChatCompletionProvider:
    return build_chat_provider(get_settings(), purpose="reasoning")


@router.post("/{ticket_id}/tools/agent-propose", response_model=ToolProposalRead, status_code=status.HTTP_201_CREATED)
def agent_propose_tool(
    ticket_id: str,
    payload: AgentToolProposeRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    provider: ChatCompletionProvider = Depends(get_reasoning_provider),
) -> ToolProposalRead:
    try:
        record = propose_agent_tool(
            session,
            ticket_id,
            user,
            payload.question,
            payload.device_id,
            embedder=embedder,
            provider=provider,
            tool_name=payload.tool_name,
            parameters=payload.parameters,
        )
    except AgentToolProposalError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except (ToolNotFoundError, TicketNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket or tool not found") from error
    except (RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The model service is unavailable. Check provider settings and connectivity.",
        ) from error
    except ToolForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not permitted here") from error
    except ToolValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return _proposal_read(record)


@router.post("/{ticket_id}/tools/agent-plan", response_model=AgentPlanRead)
def agent_plan_tools(
    ticket_id: str,
    payload: AgentToolProposeRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    provider: ChatCompletionProvider = Depends(get_reasoning_provider),
) -> AgentPlanRead:
    try:
        plan = plan_agent_tools(
            session,
            ticket_id,
            user,
            payload.question,
            payload.device_id,
            embedder=embedder,
            provider=provider,
        )
    except ToolNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error
    except TicketNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error
    except (RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The model service is unavailable. Check provider settings and connectivity.",
        ) from error
    except AgentToolProposalError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return AgentPlanRead(
        ticket_id=plan.ticket_id,
        question=plan.question,
        device_id=plan.device_id,
        summary=plan.summary,
        suggestions=[
            AgentPlanSuggestionRead(
                tool_name=item.tool_name,
                title=item.title,
                description=item.description,
                kind=item.kind,
                category=item.category,
                risk=item.risk,
                requires_confirmation=item.requires_confirmation,
                device_id=item.device_id,
                device_ref=item.device_ref,
                device_type=item.device_type,
                parameters=item.parameters,
                rationale=item.rationale,
                steps=item.steps,
                evidence=item.evidence,
                confidence=item.confidence,
                reasoning=item.reasoning,
            )
            for item in plan.suggestions
        ],
        reasoning=plan.reasoning,
        alternatives=plan.alternatives,
        intent=plan.intent,
    )


@router.get("/{ticket_id}/tools/catalog", response_model=list[ToolCatalogItemRead])
def get_tool_catalog(
    ticket_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[ToolCatalogItemRead]:
    return [
        ToolCatalogItemRead(
            name=item.name,
            title=item.title,
            description=item.description,
            kind=item.kind,
            category=item.category,
            risk=item.risk,
            requires_confirmation=item.requires_confirmation,
            target_device_types=list(item.target_device_types) if item.target_device_types else None,
        )
        for item in tool_execution.catalog(user)
    ]


@router.get("/{ticket_id}/tools", response_model=list[ToolProposalRead])
def list_tool_proposals(
    ticket_id: str,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[ToolProposalRead]:
    try:
        records = tool_execution.list_proposals(session, ticket_id, user)
    except ToolNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from error
    return [_proposal_read(record) for record in records]


@router.post("/{ticket_id}/tools/propose", response_model=ToolProposalRead, status_code=status.HTTP_201_CREATED)
def propose_tool(
    ticket_id: str,
    payload: ToolProposeRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ToolProposalRead:
    tool_name, proposed_parameters = _resolve_proposal(payload)
    parameters = {"device_id": payload.device_id, **proposed_parameters}
    try:
        record = tool_execution.propose_tool(session, ticket_id, user, tool_name, parameters)
    except ToolNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool or ticket not found") from error
    except ToolForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not permitted here") from error
    except ToolValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return _proposal_read(record)


def _resolve_proposal(payload: ToolProposeRequest) -> tuple[str, dict]:
    if payload.model_proposal is None:
        return payload.tool_name, payload.parameters

    proposed_name = payload.model_proposal.get("name")
    proposed_arguments = payload.model_proposal.get("arguments")
    if proposed_name != payload.tool_name:
        raise HTTPException(status_code=422, detail="The selected tool does not match the model proposal")
    if not isinstance(proposed_arguments, dict):
        raise HTTPException(status_code=422, detail="Model tool arguments must be an object")
    if proposed_arguments.get("device_id") != payload.device_id:
        raise HTTPException(status_code=422, detail="Model proposal device does not match the selected device")
    arguments = {key: value for key, value in proposed_arguments.items() if key != "device_id"}
    if payload.parameters and arguments != payload.parameters:
        raise HTTPException(status_code=422, detail="Submitted parameters do not match the model proposal")
    return payload.tool_name, arguments


@router.post("/{ticket_id}/tools/{proposal_id}/confirm", response_model=ToolExecutionRead)
def confirm_tool(
    ticket_id: str,
    proposal_id: str,
    payload: ToolConfirmRequest,
    session: Session = Depends(get_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ToolExecutionRead:
    try:
        record = tool_execution.confirm_tool(
            session, ticket_id, proposal_id, user, payload.confirmation_id
        )
    except ToolNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found") from error
    except ToolForbiddenError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action cannot be confirmed here",
        ) from error
    except ToolValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    if record.status == tool_execution.PROPOSED:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tool proposal is awaiting confirmation")
    return _execution_read(record)


def _proposal_read(record: tool_execution.ToolProposalRecord) -> ToolProposalRead:
    return ToolProposalRead(
        id=record.id,
        ticket_id=record.ticket_id,
        tool_name=record.tool_name,
        device_id=record.device_id,
        device_ref=record.device_ref,
        kind=record.kind,
        requires_confirmation=record.requires_confirmation,
        parameters=record.parameters,
        status=record.status,
        summary=record.summary,
        confirmation_id=record.correlation_id,
        created_at=record.created_at,
        result=record.result,
    )


def _execution_read(record: tool_execution.ToolExecutionRecord) -> ToolExecutionRead:
    return ToolExecutionRead(
        id=record.id,
        ticket_id=record.ticket_id,
        tool_name=record.tool_name,
        device_id=record.device_id,
        device_ref=record.device_ref,
        status=record.status,
        message=record.message,
        correlation_id=record.correlation_id,
        executed_at=record.executed_at,
        result=record.result,
    )
