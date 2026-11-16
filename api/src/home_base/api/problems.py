"""RFC 9457 problem details: one handler maps every DomainError (ADR-001).

The response says what went wrong in terms the founder's screen can show, never a
stack trace or personal data. Each error class has a stable `type`, so the web app
can branch on it without parsing text.
"""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from home_base.core import errors

PROBLEM_JSON = "application/problem+json"

# (status, type slug): the most specific class first.
_MAPPING: list[tuple[type[errors.DomainError], HTTPStatus, str]] = [
    (errors.NotFoundError, HTTPStatus.NOT_FOUND, "not-found"),
    (errors.NotSignedInError, HTTPStatus.UNAUTHORIZED, "not-signed-in"),
    (errors.NotOnboardedError, HTTPStatus.FORBIDDEN, "not-onboarded"),
    (errors.OnboardingError, HTTPStatus.CONFLICT, "onboarding"),
    (errors.TenantError, HTTPStatus.NOT_FOUND, "not-found"),  # never confirm another's row exists
    (errors.FactError, HTTPStatus.UNPROCESSABLE_ENTITY, "fact"),
    (errors.IntentError, HTTPStatus.UNPROCESSABLE_ENTITY, "intent"),
    (errors.StageError, HTTPStatus.UNPROCESSABLE_ENTITY, "stage"),
    (errors.DecisionError, HTTPStatus.UNPROCESSABLE_ENTITY, "decision"),
    (errors.ApplicationError, HTTPStatus.CONFLICT, "application"),
    (errors.ClockError, HTTPStatus.UNPROCESSABLE_ENTITY, "clock"),
]


def _problem(status: HTTPStatus, slug: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_JSON,
        content={
            "type": f"urn:home-base:problem:{slug}",
            "title": status.phrase,
            "status": int(status),
            "detail": detail,
        },
    )


def problem_for(exc: errors.DomainError) -> JSONResponse:
    for cls, status, slug in _MAPPING:
        if isinstance(exc, cls):
            return _problem(status, slug, str(exc))
    # Any other domain error is a rule or data problem on our side, not the caller's.
    return _problem(
        HTTPStatus.INTERNAL_SERVER_ERROR, "internal", "Something went wrong on our side."
    )


def install(app: FastAPI) -> None:
    @app.exception_handler(errors.DomainError)
    def _domain(_: Request, exc: errors.DomainError) -> JSONResponse:
        return problem_for(exc)

    @app.exception_handler(RequestValidationError)
    def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
        return _problem(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "validation",
            f"Check these fields: {', '.join(fields)}",
        )
