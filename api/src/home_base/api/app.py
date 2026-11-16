"""The FastAPI app (ADR-001). Routers only call services; no rule logic here."""

import os

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import text

from home_base.api import applications, deps, onboarding, opportunities, problems, profile, today


class Health(BaseModel):
    status: str
    git_sha: str
    migration: str | None


def create_app() -> FastAPI:
    app = FastAPI(title="Home Base API", version="0.1.0")
    problems.install(app)
    app.include_router(opportunities.router)
    app.include_router(today.router)
    app.include_router(profile.router)
    app.include_router(applications.router)
    app.include_router(onboarding.router)

    @app.get("/health", tags=["ops"])
    def health(session: deps.Db) -> Health:
        """Status, git SHA and current migration, so a deploy is checked in one call."""
        migration = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return Health(
            status="ok", git_sha=os.environ.get("GIT_SHA", "unknown"), migration=migration
        )

    return app
