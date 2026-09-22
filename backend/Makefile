# Variables
MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ENV_FILE := $(MAKEFILE_DIR)/config/.env
DOCKER_COMPOSE_FILE := $(MAKEFILE_DIR)/docker-compose.yml
POSTGRES_SERVICE := postgres
# Must match container_name for the postgres service in docker-compose.yml
POSTGRES_CONTAINER := book-rec-postgres

# -------------------
# General commands
# -------------------

# Poetry commands
.PHONY: install
install:
	poetry install

# Local development (native FastAPI)
.PHONY: dev
dev:
	LOG_LEVEL=INFO poetry run uvicorn app.main:app --reload --reload-include "*.py" --reload-include "*.env"

# The deployed service, locally: APP_ENVIRONMENT=production (the same value the
# deploy recipe sets) and no --reload, so the production-only paths are live —
# today that means the session token budget, which is read everywhere but only
# enforced here. Against the compose Postgres; for the deployed database use
# local-prod-neon.
.PHONY: local-prod
local-prod:
	APP_ENVIRONMENT=production LOG_LEVEL=INFO poetry run uvicorn app.main:app

# local-prod against Neon — the same override dev-neon uses: config/.env.neon
# holds only POSTGRES_* values, and process env beats config/.env in
# pydantic-settings. As close to the deployed service as this machine gets.
.PHONY: local-prod-neon
local-prod-neon:
	set -a && . $(MAKEFILE_DIR)config/.env.neon && set +a && $(MAKE) local-prod

# clear the pycache
.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
	find . -name "*.pyo" -delete
	find . -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null

# -------------------
# PostgreSQL commands
# -------------------

# Local development (databases + native FastAPI)
.PHONY: postgres-start
postgres-start:
	docker compose --env-file $(ENV_FILE) -f $(DOCKER_COMPOSE_FILE) up $(POSTGRES_SERVICE) -d
	@echo "Databases started. Run 'make dev' to start API"

# stop the postgres container
.PHONY: postgres-stop
postgres-stop:
	docker compose -f $(DOCKER_COMPOSE_FILE) down $(POSTGRES_SERVICE)
	@echo "PostgreSQL container stopped (does not remove volumes)"

# enter postgres CLI (loads POSTGRES_USER / POSTGRES_DB from config/.env)
.PHONY: postgres-cli
postgres-cli:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -it -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		psql -U $$POSTGRES_USER -d $$POSTGRES_DB

# run an ad hoc query file against the dev postgres container (default: data/sql_dev_commands.sql)
# usage: make postgres-query [FILE=data/some_other_file.sql]
.PHONY: postgres-query
postgres-query:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		psql -U $$POSTGRES_USER -d $$POSTGRES_DB < $(MAKEFILE_DIR)$(or $(FILE),data/sql_dev_commands.sql)

BACKUP_FILE ?= $(MAKEFILE_DIR)data/backup.sql
# restore plain-SQL backup (data/backup.sql) into the compose postgres container
.PHONY: postgres-restore
postgres-restore:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		psql -U $$POSTGRES_USER -d $$POSTGRES_DB < $(BACKUP_FILE)

# dump the postgres data to a file (overwrites existing backup.sql)
# currently throw an error because entry point init and backup does have IF NOT EXISTS
.PHONY: postgres-dump
postgres-dump:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB > $(MAKEFILE_DIR)data/backup.sql
	@echo "PostgreSQL data dumped to $(MAKEFILE_DIR)data/backup.sql"

# restore the postgres books data from a file
.PHONY: postgres-restore-books
postgres-restore-books:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		psql -U $$POSTGRES_USER -d $$POSTGRES_DB < $(MAKEFILE_DIR)data/backup/backup.sql
	@echo "PostgreSQL data restored from $(MAKEFILE_DIR)data/backup/backup.sql

# dump chat_runs data to a timestamped .sql file (data only, restorable via psql <)
.PHONY: postgres-dump-chat-runs
postgres-dump-chat-runs:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB --table=chat_runs --data-only --column-inserts \
		> $(MAKEFILE_DIR)data/chat_runs_$$(date +%Y%m%d_%H%M%S).sql
	@echo "chat_runs dumped to $(MAKEFILE_DIR)data/"

# dump feedback data to a timestamped .sql file (data only, restorable via psql <)
.PHONY: postgres-dump-feedback
postgres-dump-feedback:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB --table=feedback --data-only --column-inserts \
		> $(MAKEFILE_DIR)data/feedback_$$(date +%Y%m%d_%H%M%S).sql
	@echo "feedback dumped to $(MAKEFILE_DIR)data/"

# dump test_runs data to a timestamped .sql file (data only, restorable via psql <)
# — the suite/case links written by evals/run_suites.py, keyed by chat_id
.PHONY: postgres-dump-test-runs
postgres-dump-test-runs:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB --table=test_runs --data-only --column-inserts \
		> $(MAKEFILE_DIR)data/test_runs_$$(date +%Y%m%d_%H%M%S).sql
	@echo "test_runs dumped to $(MAKEFILE_DIR)data/"

# dump chat_runs plus every table FK'd to it (feedback, test_runs) into ONE
# timestamped .sql file, so the set is restored/moved together. pg_dump
# topo-sorts data-only dumps by FK dependency, so chat_runs's INSERTs land
# before feedback's/test_runs's in the file — required since these are plain
# (non-deferred) constraints: a referencing row inserted before its chat_runs
# row would fail. Restore with: make postgres-query FILE=data/<this file>
.PHONY: postgres-dump-chat-runs-cascade
postgres-dump-chat-runs-cascade:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB \
			--table=chat_runs --table=feedback --table=test_runs \
			--data-only --column-inserts \
		> $(MAKEFILE_DIR)data/chat_runs_cascade_$$(date +%Y%m%d_%H%M%S).sql
	@echo "chat_runs + feedback + test_runs dumped to $(MAKEFILE_DIR)data/"

# wipe all recorded chat runs (dev convenience — irreversible)
# CASCADE: feedback.chat_id and test_runs.chat_id both reference chat_runs,
# and TRUNCATE refuses a table with incoming FK references (even empty ones)
# unless told to cascade — this also empties feedback and test_runs.
# NOTE: for dev
.PHONY: postgres-clear-chat-runs
postgres-clear-chat-runs:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		psql -U $$POSTGRES_USER -d $$POSTGRES_DB -c "TRUNCATE TABLE chat_runs CASCADE;"
	@echo "chat_runs table cleared (feedback, test_runs cascaded)"

# wipe all recorded feedback (dev convenience — irreversible)
# NOTE: for dev
.PHONY: postgres-clear-feedback
postgres-clear-feedback:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		psql -U $$POSTGRES_USER -d $$POSTGRES_DB -c "TRUNCATE TABLE feedback;"
	@echo "feedback table cleared"

# wipe all recorded suite/case links (dev convenience — irreversible).
# Standalone use only — postgres-clear-chat-runs already cascades into this
# table, so postgres-logs-clear doesn't need to call it too.
# NOTE: for dev
.PHONY: postgres-clear-test-runs
postgres-clear-test-runs:
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		psql -U $$POSTGRES_USER -d $$POSTGRES_DB -c "TRUNCATE TABLE test_runs;"
	@echo "test_runs table cleared"

# dump the local container's books table (data only, COPY format) — the seed
# for neon-bootstrap. No --column-inserts: 5,197 rows x 1024 floats as
# individual INSERTs would be enormous and slow to replay.
.PHONY: postgres-dump-books
postgres-dump-books:
	@mkdir -p $(MAKEFILE_DIR)data/backup
	set -a && . $(ENV_FILE) && set +a && \
	docker exec -i -e PGPASSWORD=$$POSTGRES_PASSWORD $(POSTGRES_CONTAINER) \
		pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB --table=books --data-only \
		> $(MAKEFILE_DIR)data/backup/books.sql
	@echo "books dumped to $(MAKEFILE_DIR)data/backup/books.sql"

# -------------------
# Neon (managed Postgres)
# -------------------

# Every target goes through the Neon CLI: `neon psql` resolves the project from
# the .neon file `neon link` wrote in this folder and fetches the password from
# your Neon login, so no operator credential sits in config/.env and a mistyped
# host can never point these at the local container. Direct endpoint, not the
# -pooler one, which is what dumps and schema changes need.

# psql shell on Neon:   make neon-cli
# one file or command:  make neon-cli ARGS='-c "SELECT count(*) FROM books;"'
.PHONY: neon-cli
neon-cli:
	neon psql -- $(ARGS)

# seed a fresh Neon database (make postgres-dump-books first). The order is
# load-bearing: the books load needs the vector type from 00_extensions, and
# ivfflat builds its centroids from the rows present when the index is created,
# so 02_indexes runs last — built on an empty table, recall degrades silently.
.PHONY: neon-bootstrap
neon-bootstrap:
	neon psql -- -v ON_ERROR_STOP=1 -f $(MAKEFILE_DIR)db/init/00_extensions.sql
	neon psql -- -v ON_ERROR_STOP=1 -f $(MAKEFILE_DIR)db/init/01_tables.sql
	neon psql -- -v ON_ERROR_STOP=1 -f $(MAKEFILE_DIR)data/backup/books.sql
	neon psql -- -v ON_ERROR_STOP=1 -f $(MAKEFILE_DIR)db/init/02_indexes.sql
	@echo "Neon bootstrapped."

# the API against Neon instead of the compose container: config/.env.neon holds
# only POSTGRES_* values, and process env beats config/.env in pydantic-settings
.PHONY: dev-neon
dev-neon:
	set -a && . $(MAKEFILE_DIR)config/.env.neon && set +a && $(MAKE) dev

# -------------------
# Deploy (Cloud Run)
# -------------------

# The recipe below is the whole description of the service: every flag that
# shapes the deployed revision is here, so nothing lives only in the console
# and a redeploy can't quietly drop a setting someone clicked in once.
CLOUD_RUN_SERVICE := book-shelf-api
CLOUD_RUN_REGION  := us-east5
GCP_PROJECT       := tuanqpham0921
# A dedicated service account, not the compute default (which carries project
# Editor): this one may only read the two secrets below.
CLOUD_RUN_SA      := $(CLOUD_RUN_SERVICE)@$(GCP_PROJECT).iam.gserviceaccount.com
# Firebase serves the site on both hostnames, so both must be allowed.
ALLOW_ORIGINS     := https://tuanqpham0921.web.app,https://tuanqpham0921.firebaseapp.com

# Deploy the backend. Builds from source via Cloud Build (no cloudbuild.yaml:
# the Dockerfile and these flags already say everything one would contain),
# pushes to Artifact Registry, and rolls out a new revision.
#
# Database settings are read from config/.env.neon — the same file `dev-neon`
# uses, so the deployed database and your local Neon runs cannot drift, and the
# endpoint host stays out of version control. The password is NOT passed here:
# it and the OpenAI key come from Secret Manager, which is what keeps them out
# of the revision's env (revisions are immutable and readable forever).
.PHONY: deploy
deploy:
	set -a && . $(MAKEFILE_DIR)config/.env.neon && set +a && \
	gcloud run deploy $(CLOUD_RUN_SERVICE) \
		--source=$(MAKEFILE_DIR) \
		--project=$(GCP_PROJECT) \
		--region=$(CLOUD_RUN_REGION) \
		--service-account=$(CLOUD_RUN_SA) \
		--allow-unauthenticated \
		--cpu=1 --memory=1Gi --cpu-boost \
		--timeout=300 \
		--min-instances=0 --max-instances=3 --concurrency=5 \
		--startup-probe=httpGet.path=/ready,initialDelaySeconds=5,periodSeconds=5,timeoutSeconds=5,failureThreshold=6 \
		--set-env-vars="^@^APP_NAME=book-shelf-backend@APP_ENVIRONMENT=production@APP_ALLOW_ORIGINS=$(ALLOW_ORIGINS)@POSTGRES_HOST=$$POSTGRES_HOST@POSTGRES_PORT=$$POSTGRES_PORT@POSTGRES_DB=$$POSTGRES_DB@POSTGRES_USER=$$POSTGRES_USER@POSTGRES_SSL_MODE=$$POSTGRES_SSL_MODE@POSTGRES_MIN_CONNECTIONS=$$POSTGRES_MIN_CONNECTIONS@POSTGRES_MAX_CONNECTIONS=$$POSTGRES_MAX_CONNECTIONS@OPENAI_BASE_MODEL=gpt-4.1-mini@OPENAI_TOKENIZER_ENCODING=o200k_base@OPENAI_EMBEDDING_MODEL=text-embedding-3-large@OPENAI_EMBEDDING_DIMENSIONS=1024@OPENAI_MAX_CONCURRENCY=10" \
		--set-secrets=POSTGRES_PASSWORD=postgres-password:latest,OPENAI_API_KEY=openai-api-key:latest
	@$(MAKE) deploy-check

# `^@^` is load-bearing above: it switches gcloud's list delimiter from `,` to
# `@`, so the commas inside APP_ALLOW_ORIGINS don't split into malformed vars.

# prove the live revision is serving: /ready runs a real query against Neon,
# so a 200 here means image, env, secrets and database are all wired up.
.PHONY: deploy-check
deploy-check:
	@URL=$$(gcloud run services describe $(CLOUD_RUN_SERVICE) \
		--project=$(GCP_PROJECT) --region=$(CLOUD_RUN_REGION) \
		--format='value(status.url)'); \
	echo "$$URL"; \
	curl -fsS -w '\n' "$$URL/ready" || (echo "NOT READY"; exit 1)

# kill switch: drop public access so every request gets a 403 and nothing runs
# (min-instances=0) or reaches OpenAI. The service and its URL stay; `deploy-on`
# restores access without a rebuild (`make deploy` also does, since
# --allow-unauthenticated re-adds this binding).
.PHONY: deploy-off
deploy-off:
	gcloud run services remove-iam-policy-binding $(CLOUD_RUN_SERVICE) \
		--member=allUsers --role=roles/run.invoker \
		--region=$(CLOUD_RUN_REGION) --project=$(GCP_PROJECT)

.PHONY: deploy-on
deploy-on:
	gcloud run services add-iam-policy-binding $(CLOUD_RUN_SERVICE) \
		--member=allUsers --role=roles/run.invoker \
		--region=$(CLOUD_RUN_REGION) --project=$(GCP_PROJECT)
	@$(MAKE) deploy-check

# -------------------
# Docker commands
# -------------------

# clean the docker containers and volumes
.PHONY: docker-clean-all
docker-clean-all:
	docker compose --env-file $(ENV_FILE) -f $(DOCKER_COMPOSE_FILE) down -v
	@echo "Docker containers and volumes cleaned"

# -------------------
# Testing commands
# -------------------

.PHONY: tests
tests:
	poetry run pytest -s tests/unit/

# in-process API tests: real FastAPI app over httpx ASGI transport, stores
# faked via dependency_overrides — no DB or LLM needed, safe to run anywhere
.PHONY: tests-integration
tests-integration:
	poetry run pytest -s tests/integration/

# the airglider library's own suite — no app imports, runs standalone
.PHONY: tests-airglider
tests-airglider:
	poetry run pytest -s airglider/tests/

.PHONY: tests-all
tests-all:
	poetry run pytest -s tests/unit/ tests/integration/ airglider/tests/

.PHONY: typecheck
typecheck:
	poetry run pyright

.PHONY: playground
playground:
	poetry run python playground/scratch.py

.PHONY: local-end-to-end-test
local-end-to-end-test:
	./tests/scripts/local_end_to_end_test.sh

# Query-suite / eval-run commands (query-suite, query-suite-all, ...) live in
# evals/makefile, next to the suite JSONs and runner they drive. Pulled in here
# so they still run as `make query-suite-all` from backend/ (cwd stays backend/,
# so the relative suite/log paths in those recipes resolve).
include $(MAKEFILE_DIR)evals/makefile

# .Phony: lint
# lint:
# 	poetry run ruff check --fix clients/ tests/unit/clients/
#   poetry run black common/utils/ tests/unit/common/utils/
