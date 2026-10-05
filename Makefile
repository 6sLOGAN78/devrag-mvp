# devRag developer entry points. Paths are quoted so a space or '@' in the checkout path works.
# Targets that call scripts created by later plans are declarative here and are exercised in
# plans 01-04 (stack), 01-13 and 01-15 (clean-room, generators).

COMPOSE_PROJECT ?= devrag-stack
COMPOSE_FILES = -f docker/docker-compose.yml -f docker/docker-compose.dev.yml
ENV_FILE = docker/.env
COMPOSE = docker compose -p $(COMPOSE_PROJECT) --env-file $(ENV_FILE)

.PHONY: ci test-unit test-live init-env preflight up infra-up down clean-room gen

ci:
	cd "$(CURDIR)" && uv run python scripts/ci/run_all.py
	cd "$(CURDIR)" && uv run ruff check --select S,ASYNC,FIX001,FIX002 --ignore S603,S607 .

test-unit:
	cd "$(CURDIR)" && uv run python run_tests.py -m unit
	cd "$(CURDIR)" && if [ -f go.mod ]; then go test -race ./internal/...; else echo "skipped: go.mod absent"; fi
	cd "$(CURDIR)" && if [ -f web/package.json ]; then (cd web && npm run test -- --run); else echo "skipped: web/package.json absent"; fi

test-live:
	cd "$(CURDIR)" && scripts/wait_stack.sh && uv run python run_tests.py -m "integration or e2e" && go test -tags=integration,e2e ./... && (cd web && npm run test:live)

init-env:
	cd "$(CURDIR)" && scripts/init_env.sh

preflight:
	cd "$(CURDIR)" && scripts/preflight.sh

up: preflight
	cd "$(CURDIR)" && $(COMPOSE) $(COMPOSE_FILES) --profile cpu --profile elasticsearch up -d --build
	cd "$(CURDIR)" && scripts/wait_stack.sh

infra-up:
	cd "$(CURDIR)" && $(COMPOSE) -f docker/docker-compose.yml --profile elasticsearch up -d
	cd "$(CURDIR)" && scripts/wait_stack.sh --infra-only

# Stop only; volumes are never removed here (the guarded removal lives in scripts/clean_room.sh).
down:
	cd "$(CURDIR)" && $(COMPOSE) $(COMPOSE_FILES) down

clean-room:
	cd "$(CURDIR)" && scripts/clean_room.sh

gen:
	cd "$(CURDIR)" && uv run python scripts/gen_routes.py
	cd "$(CURDIR)" && if [ -f scripts/gen_go_entities.py ]; then uv run python scripts/gen_go_entities.py; fi
