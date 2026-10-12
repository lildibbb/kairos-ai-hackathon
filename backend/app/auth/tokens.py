from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError

from app.config import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
SUPPORTED_ROLES = frozenset({"operator", "technician", "supervisor", "customer"})


def create_access_token(user_id: str, role: str, *, now: datetime | None = None) -> tuple[str, datetime]:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + ACCESS_TOKEN_TTL
    token = jwt.encode(
        {"sub": user_id, "role": role, "iat": issued_at, "exp": expires_at},
        get_settings().jwt_secret,
        algorithm=ALGORITHM,
    )
    return token, expires_at


def decode_access_token(token: str) -> dict[str, str]:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        subject = payload.get("sub")
        role = payload.get("role")
        issued_at = payload.get("iat")
        if not isinstance(subject, str) or not subject:
            raise InvalidTokenError("Required claims are missing")
        if not isinstance(role, str) or role not in SUPPORTED_ROLES:
            raise InvalidTokenError("Unsupported role")
        if not isinstance(issued_at, (int, float)) or isinstance(issued_at, bool):
            raise InvalidTokenError("Invalid issued-at claim")
        if issued_at > datetime.now(UTC).timestamp():
            raise InvalidTokenError("Token issue time is in the future")
        return {"sub": subject, "role": role}
    except InvalidTokenError as error:
        raise ValueError("Invalid or expired access token") from error
