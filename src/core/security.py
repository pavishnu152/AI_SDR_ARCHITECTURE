"""
Password hashing + JWT issuance/verification.

Why JWT instead of server-side sessions: this API is meant to be called by
a frontend SPA and potentially other clients later (a CLI, a batch script)
— a stateless bearer token means any client authenticates the same way
without the server tracking session state anywhere. The tradeoff (a token
can't be instantly revoked before it expires) is exactly why
JWT_EXPIRE_MINUTES defaults to 60, not something long-lived — short expiry
bounds the blast radius of a leaked token instead of relying on revocation
infrastructure we haven't built.

Why bcrypt via passlib instead of a faster hash (SHA-256, etc.): password
hashing must be deliberately slow to resist brute-force/rainbow-table
attacks. bcrypt (and its cost factor) is the industry-standard choice for
exactly this reason — using a fast general-purpose hash for passwords is a
classic, avoidable security mistake.
"""
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Returns the token's subject (user email) if valid, else None. Never
    raises — callers treat None as "not authenticated", not a crash."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None
