from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, BearerCredentials, CurrentUser
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, auth_service: AuthServiceDep) -> TokenResponse:
    user, token = auth_service.register(payload)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, auth_service: AuthServiceDep) -> TokenResponse:
    user, token = auth_service.login(payload)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.post("/logout", response_model=MessageResponse)
def logout(
    credentials: BearerCredentials,
    auth_service: AuthServiceDep,
) -> MessageResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return MessageResponse(message="Logged out.")
    auth_service.logout(credentials.credentials)
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=UserPublic)
def me(current_user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(current_user)
