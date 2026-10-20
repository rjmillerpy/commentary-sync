.PHONY: install lint test benchmark check web-install web-check client-check listener-check listener-dev web-dev e2e-install e2e-check infra-check e2e up down migration events

# The e2e stack: compose.yaml with compose.e2e.yaml on top, as its own project.
E2E_COMPOSE = docker compose -f compose.yaml -f compose.e2e.yaml -p commentary-sync-e2e

# The compose stack's Postgres, as published on localhost (see compose.yaml).
LOCAL_DATABASE_URL = postgresql+psycopg://commentary:$${COMMENTARY_DB_PASSWORD:-commentary-local}@127.0.0.1:5434/commentary

# Install the locked environment, the studio's packages and the git hook.
install: web-install e2e-install
	uv sync --locked --all-packages
	uv run pre-commit install

# The JavaScript workspaces (client/, web/), exactly as locked, from the
# root package-lock.json. --ignore-scripts: no dependency runs code at
# install time; nothing here needs it.
web-install:
	npm ci --ignore-scripts

# The e2e tests' packages, for type checking here; the e2e image installs its own.
e2e-install:
	cd e2e && npm ci --ignore-scripts

# Every pre-commit hook on every file: ruff, ruff format, bandit, mypy, secrets.
lint:
	uv run pre-commit run --all-files

# Tests with coverage; fails under the floor set in pyproject.toml.
test:
	uv run pytest

# Synthetic accuracy benchmark, about 30 s.
benchmark:
	uv run sync-benchmark

# The studio: eslint, tsc --noEmit, and Jest with its coverage floor.
web-check:
	npm run check --workspace web

# The listener app: eslint, tsc --noEmit, Jest (jest-expo) with a 90% floor.
listener-check:
	npm run check --workspace listener

# The listener app in Expo's dev server: scan the QR code with Expo Go.
# A phone needs EXPO_PUBLIC_API_URL; see README, "The listener app".
listener-dev:
	npm run start --workspace listener

# The shared API client: tsc, and Node's own test runner with a 90% floor.
client-check:
	npm run check --workspace client

# The studio on http://localhost:3000 with hot reload, against `make up`'s API.
web-dev:
	npm run dev --workspace web

# The e2e tests type-check (strict) and their compose file is valid. Running
# them is `make e2e`.
e2e-check:
	cd e2e && npm run typecheck
	$(E2E_COMPOSE) config --quiet

# The AWS deployment (infra/), offline: format, validate, the mock-provider
# tests, tflint and Checkov. No AWS credentials; nothing is applied.
infra-check:
	cd infra && terraform fmt -check -recursive
	cd infra && terraform init -backend=false -input=false > /dev/null
	cd infra && terraform validate
	cd infra && terraform test
	infra/lint.sh

# What CI checks.
check: lint test client-check web-check listener-check e2e-check infra-check

# End-to-end, about 3 minutes: builds and starts a separate stack with no
# internet and no published ports, adds a game, runs the Playwright tests in
# a browser inside it, then deletes the stack. Fails if a test fails; the HTML
# report, any failure's trace and the API's log are in e2e/results/.
e2e:
	mkdir -p e2e/results
	$(E2E_COMPOSE) up --build --detach --wait
	$(E2E_COMPOSE) run --rm seed
	$(E2E_COMPOSE) build playwright
	$(E2E_COMPOSE) run --rm --user "$$(id -u):$$(id -g)" playwright; \
		status=$$?; $(E2E_COMPOSE) logs --no-color api > e2e/results/api.log; \
		$(E2E_COMPOSE) down --volumes; exit $$status

# Build the images and start the stack (API, studio, Postgres, Redis, LiveKit,
# scheduler); returns once healthy. The studio is on http://localhost:3000.
up:
	docker compose up --build --detach --wait

# Stop the stack and delete its data volume.
down:
	docker compose down --volumes

# Write a migration from the difference between the models and the running
# stack's database: `make up`, then `make migration m="add commentators"`.
# Read the generated file before committing it.
migration:
	COMMENTARY_DATABASE_URL="$(LOCAL_DATABASE_URL)" COMMENTARY_CACHE_URL=redis://127.0.0.1:6379/0 \
		COMMENTARY_AUTH_SECRET=local-only-auth-secret-not-for-deployment \
		COMMENTARY_LIVEKIT_URL=ws://localhost:7880 COMMENTARY_LIVEKIT_API_KEY=local-livekit-key \
		COMMENTARY_LIVEKIT_API_SECRET=local-only-livekit-secret-not-for-deployment uv run alembic revision --autogenerate -m "$(m)"

# Import the next 7 days of NFL and NBA games now, without waiting for the
# scheduler service.
events:
	docker compose exec api python -m app.events.cli --league nfl
	docker compose exec api python -m app.events.cli --league nba
