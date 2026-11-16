# ADR-005: Background jobs

Status: Accepted, 2026-11-10 · Owner: Andrew

## Context

Background work in Phase 1 is small and infrequent: recalculating matches after a fact, intent or re-check change (INT-04, FRS-06), requirement extraction and draft answers through the AI adapter, and re-check reminders. Each job must be traceable in `job_runs` (plan, week 2). Postgres is already the one stateful service.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| A Postgres table as the queue, claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, one worker process | No new service; a job can be enqueued in the same transaction as the change and its audit event; `job_runs` is the queue's own history | We write and test the worker loop and retry logic ourselves |
| A Postgres-backed job library | Retries and scheduling built in | One more dependency to learn and pin; must still write to `job_runs` |
| Redis with a task queue | Common | A second stateful service to host, secure and back up; excluded by the handbook unless a real need appears |

## Decision

A Postgres table as the queue, with one worker process in `home_base/jobs/`. Revisit a library only if the hand-written loop grows past retries and a schedule.

## Consequences

- Enqueueing is transactional: a change, its audit event and its follow-up job commit or roll back together.
- Jobs are idempotent and keyed, so a retry never double-applies a recalculation.
- The worker runs the same image as the API with a different command; Docker Compose gains a `worker` service.
- No Redis in Phase 1.
