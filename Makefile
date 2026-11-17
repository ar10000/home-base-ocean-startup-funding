# One command per check (handbook section 8). Nothing is "done" until `make all` passes.
# Targets for parts not built yet (evals) are added with those parts.

API := cd api && uv run
WEB := cd web && npm run
# The local stack only (infra/docker-compose.yml); nothing here points at a hosted service.
DEV_ENV := HOME_BASE_DATABASE_URL=postgresql+psycopg://home_base:home_base_local@127.0.0.1:54320/home_base \
	HOME_BASE_OIDC_ISSUER=http://localhost:8080/realms/home-base HOME_BASE_OIDC_AUDIENCE=home-base-api
# The AI provider for local commands (ADR-009): AI=fake (default, no network), AI=anthropic
# (D-84) or AI=mistral, each loading its key from a file outside the repository
# (~/.config/home-base/<provider>.env). The key is passed to the process only; nothing
# prints it. Fictional data only.
AI ?= fake
KEY_ENV = $(HOME)/.config/home-base/$(AI).env
MISTRAL_BASE_URL ?= https://api.eu.mistral.ai
AI_ENV = $(if $(filter mistral anthropic,$(AI)),test -f $(KEY_ENV) || { echo "no $(KEY_ENV): see the README (Run it locally)"; exit 2; }; set -a; . $(KEY_ENV); set +a;) \
	export HOME_BASE_AI_PROVIDER=$(AI) HOME_BASE_MISTRAL_BASE_URL=$(MISTRAL_BASE_URL);

.PHONY: setup check test db-up db-check rules mutation demo client web dev-up dev-api dev-web e2e demo-seed demo-record demo-build evals all

setup:  ## install tools and git hooks
	cd api && uv sync
	cd api && uv run pre-commit install --install-hooks -t pre-commit -t commit-msg -t pre-push
	cd web && npm ci

check:  ## lint, format, types, rule traceability
	$(API) ruff format --check src tests alembic ../scripts
	$(API) ruff check src tests alembic ../scripts
	$(API) mypy
	$(API) mypy --strict ../scripts
	$(API) python ../scripts/check_rules.py --check

test:  ## unit and integration tests with branch coverage (handbook: 85% overall, rules.py at 100%); needs Docker
	$(API) pytest --cov --cov-branch --cov-fail-under=85

db-up:  ## start the local Postgres 16 (infra/docker-compose.yml)
	docker compose -f infra/docker-compose.yml up -d --wait postgres

db-check:  ## fail when the models and the migrations disagree (handbook section 11); needs Docker
	$(API) pytest -q tests/integration/test_migrations.py

rules:  ## regenerate docs/rules/traceability.md after changing the catalogue
	$(API) python ../scripts/check_rules.py

mutation:  ## mutation tests on rules.py and domain.py (handbook: 90% killed, matching and today 100%)
	$(API) mutmut run
	cd api && uv run mutmut results --all true | uv run python ../scripts/check_mutation.py

demo:  ## Week 1 demo: Today for the fictional sample company over the fictional fixtures
	$(API) python ../scripts/demo_today.py --seed-dir tests/fixtures/seed --today 2026-11-10

client:  ## regenerate the TypeScript API client (web/src/api/) from the API's OpenAPI document
	$(API) python ../scripts/export_openapi.py
	$(WEB) client

web:  ## web app: format, lint, types, tests with coverage (handbook: 70% on features/), build
	$(WEB) format:check
	$(WEB) lint
	$(WEB) typecheck
	$(WEB) test
	$(WEB) build

dev-up:  ## local stack: Postgres and Keycloak, migrations, fictional opportunities; needs Docker
	docker compose -f infra/docker-compose.yml up -d --wait postgres keycloak
	cd api && $(DEV_ENV) uv run alembic upgrade head
	cd api && $(DEV_ENV) uv run python ../scripts/dev_seed.py

dev-api:  ## the API on 127.0.0.1:8000 against the local stack, reloading on change
	cd api && $(AI_ENV) $(DEV_ENV) uv run uvicorn --factory home_base.api.app:create_app --reload --reload-dir src --host 127.0.0.1 --port 8000

dev-web:  ## the web app on http://localhost:5173, /api proxied to the local API
	$(WEB) dev

e2e:  ## Playwright golden path against the local stack (run make dev-up first); starts the API and web app if needed
	cd web && npx playwright install chromium
	$(WEB) e2e

evals:  ## the AI evaluation sets against the handbook's thresholds; local stack, provider from HOME_BASE_AI_PROVIDER
	cd api && $(AI_ENV) $(DEV_ENV) uv run python ../scripts/run_evals.py

demo-seed:  ## load the public demo's fictional calls (scripts/demo/seed) into the local stack
	cd api && $(DEV_ENV) uv run python ../scripts/dev_seed.py --seed-dir ../scripts/demo/seed

demo-record:  ## re-record the demo snapshot from the local stack (after demo-seed, dev-api, dev-web)
	cd web && npx playwright install chromium && node e2e/record-demo.mjs && npx prettier --write src/demo/snapshot.json

demo-build:  ## the static demo (D-79) into web/dist-demo; DEMO_BASE is the path it is served from
	cd web && VITE_DEMO=1 VITE_BASE=$(or $(DEMO_BASE),/) npx vite build --outDir dist-demo \
		&& cp dist-demo/index.html dist-demo/404.html

all: check test web  ## the fast checks CI runs, in CI's order; CI also runs `make mutation` as its own job
