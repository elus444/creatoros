from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.project import Project
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.content_service import ContentService
from app.services.project_service import ProjectService
from app.services.trend_service import TrendService

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(db: Annotated[Session, Depends(get_db)]) -> AuthService:
    return AuthService(db)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_service.authenticate_token(credentials.credentials)


def get_project_service(db: Annotated[Session, Depends(get_db)]) -> ProjectService:
    return ProjectService(db)


def get_trend_service(db: Annotated[Session, Depends(get_db)]) -> TrendService:
    return TrendService(db)


def get_content_service(db: Annotated[Session, Depends(get_db)]) -> ContentService:
    return ContentService(db)


def get_owned_project(
    project_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> Project:
    return project_service.get_owned(current_user, project_id)


CurrentUser = Annotated[User, Depends(get_current_user)]
DBSession = Annotated[Session, Depends(get_db)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
TrendServiceDep = Annotated[TrendService, Depends(get_trend_service)]
ContentServiceDep = Annotated[ContentService, Depends(get_content_service)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]
