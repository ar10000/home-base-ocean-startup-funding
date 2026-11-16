# ADR-001: Web framework

Status: Accepted, 2026-11-10 · Owner: Andrew

## Context

The API serves the web app through a TypeScript client generated from OpenAPI (handbook section 2: decided). Validation is Pydantic v2, persistence is SQLAlchemy 2.0 with Alembic. The rules are pure functions that already exist (Week 1); the framework only adds routes, request and response models, and RFC 9457 errors (plan, week 2).

## Options considered

| Option | For | Against |
| --- | --- | --- |
| FastAPI | OpenAPI generated from typed models, so the client matches by construction; Pydantic v2 native; dependency injection fits per-request `today` and tenant | Async by default; we keep handlers sync unless there is a reason |
| Flask (with an OpenAPI extension) | Familiar, small | OpenAPI and validation come from extensions, so the contract can drift from the code |
| Django REST Framework | Batteries included | Its ORM and admin duplicate SQLAlchemy and Alembic, already decided |

## Decision

FastAPI. Routers live in `home_base/api/` and only call services; no rule logic in a route.

## Consequences

- The OpenAPI document is the contract; CI regenerates the web client and fails on a diff.
- Errors are RFC 9457 problem details from one exception handler that maps `DomainError` subclasses.
- Sync handlers and a sync SQLAlchemy session to start; moving to async is a later ADR if load needs it.
