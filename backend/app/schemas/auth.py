from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserPublic


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class MeResponse(UserPublic):
    """Current user plus a sliding access token so active sessions stay signed in."""

    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str
