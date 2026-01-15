from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import redis as redis_client
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower()))

    def get_user_by_id(self, user_id: str) -> User | None:
        try:
            parsed_id = UUID(user_id)
        except (TypeError, ValueError):
            return None
        return self.db.get(User, parsed_id)

    def register(self, payload: RegisterRequest) -> tuple[User, str]:
        existing = self.get_user_by_email(payload.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            full_name=payload.full_name.strip() if payload.full_name else None,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        token, _, _ = create_access_token(str(user.id))
        return user, token

    def login(self, payload: LoginRequest) -> tuple[User, str]:
        user = self.get_user_by_email(payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        token, _, _ = create_access_token(str(user.id))
        return user, token

    def logout(self, token: str) -> None:
        try:
            payload = decode_access_token(token)
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
            ) from exc

        jti = payload.get("jti")
        exp = payload.get("exp")
        if not isinstance(jti, str) or exp is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload.",
            )

        expires_at = datetime.fromtimestamp(int(exp), tz=UTC)
        remaining = int((expires_at - datetime.now(UTC)).total_seconds())
        redis_client.blacklist_token(jti, remaining)

    def authenticate_token(self, token: str) -> User:
        try:
            payload = decode_access_token(token)
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        jti = payload.get("jti")
        if not isinstance(jti, str) or redis_client.is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = self.get_user_by_id(subject)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
