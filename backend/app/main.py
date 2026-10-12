from fastapi import FastAPI

from app.api.assistant import router as assistant_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.customers import router as customers_router
from app.api.customer_portal import router as customer_portal_router
from app.api.customer_reports import router as customer_reports_router
from app.api.events import router as events_router
from app.api.knowledge import router as knowledge_router
from app.api.tickets import router as tickets_router
from app.api.tools import router as tools_router

app = FastAPI(title="Field Force Incident Assistant")
app.include_router(auth_router)
app.include_router(events_router)
app.include_router(tickets_router)
app.include_router(assistant_router)
app.include_router(tools_router)
app.include_router(audit_router)
app.include_router(customers_router)
app.include_router(customer_portal_router)
app.include_router(customer_reports_router)
app.include_router(knowledge_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
