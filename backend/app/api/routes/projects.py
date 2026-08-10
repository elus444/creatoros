from fastapi import APIRouter, status

from app.api.deps import CurrentUser, OwnedProject, ProjectServiceDep
from app.schemas.project import ProjectCreate, ProjectPublic

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectPublic])
def list_projects(
    current_user: CurrentUser,
    project_service: ProjectServiceDep,
) -> list[ProjectPublic]:
    projects = project_service.list_for_user(current_user)
    return [ProjectPublic.model_validate(project) for project in projects]


@router.post("", response_model=ProjectPublic, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: CurrentUser,
    project_service: ProjectServiceDep,
) -> ProjectPublic:
    project = project_service.create(current_user, payload)
    return ProjectPublic.model_validate(project)


@router.get("/{project_id}", response_model=ProjectPublic)
def get_project(project: OwnedProject) -> ProjectPublic:
    return ProjectPublic.model_validate(project)
