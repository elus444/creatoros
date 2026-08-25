from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate


class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user: User) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.user_id == user.id)
            .order_by(Project.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def create(self, user: User, payload: ProjectCreate) -> Project:
        project = Project(
            user_id=user.id,
            name=payload.name.strip(),
            niche=payload.niche.strip() if payload.niche else None,
            audience=payload.audience.strip() if payload.audience else None,
            brand_voice=payload.brand_voice.strip() if payload.brand_voice else None,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get_owned(self, user: User, project_id: UUID) -> Project:
        project = self.db.get(Project, project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )
        return project
