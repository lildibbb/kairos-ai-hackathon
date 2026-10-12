from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings, get_settings
from app.db.session import get_session
from app.domain.models import CustomerAccount, User
from app.main import app
from app.seed.workforce_data import generate_dataset, ingest_dataset


def _settings(**overrides) -> Settings:
    base = dict(customer_chat_provider="local", embedding_provider="local", model_tls_verify=True,
                app_environment="development")
    base.update(overrides)
    return Settings(**base)


def _client(session, settings):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_mock_login_provisions_customer_and_issues_working_token(db_session, enable_demo_seed):
    ingest_dataset(db_session, generate_dataset(customers=8))
    settings = _settings(customer_mock_customer_ref="SYN-00042-0002")
    client = _client(db_session, settings)
    try:
        with client:
            response = client.post("/portal/auth/login")
            assert response.status_code == 200
            body = response.json()
            assert body["role"] == "customer"
            user = db_session.scalar(select(User).where(User.email == "customer.demo@invalid"))
            assert user is not None and body["user_id"] == user.id
            assert db_session.get(CustomerAccount, user.id) is not None
            me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
            assert me.status_code == 200 and me.json()["role"] == "customer"
    finally:
        app.dependency_overrides.clear()


def test_mock_login_is_idempotent_across_calls(db_session, enable_demo_seed):
    ingest_dataset(db_session, generate_dataset(customers=8))
    client = _client(db_session, _settings())
    try:
        with client:
            first = client.post("/portal/auth/login").json()
            second = client.post("/portal/auth/login").json()
            assert first["user_id"] == second["user_id"]
    finally:
        app.dependency_overrides.clear()


def test_mock_login_refused_in_production(db_session, enable_demo_seed):
    ingest_dataset(db_session, generate_dataset(customers=8))
    client = _client(db_session, _settings(app_environment="production"))
    try:
        with client:
            assert client.post("/portal/auth/login").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_mock_login_conflict_when_household_missing(db_session, enable_demo_seed):
    ingest_dataset(db_session, generate_dataset(customers=8))
    client = _client(db_session, _settings(customer_mock_customer_ref="SYN-99999-0001"))
    try:
        with client:
            assert client.post("/portal/auth/login").status_code == 409
    finally:
        app.dependency_overrides.clear()
