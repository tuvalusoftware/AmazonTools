.PHONY: install start run run-job login test test-integration preview-digest reset-db pull-deploy

# Catch-all rule so extra path arguments after a target are not treated as unknown targets.
%:
	@:

VENV   = .venv
PYTHON = $(VENV)/bin/python
PIP    = $(VENV)/bin/pip
PYTHON3 = python3.11

install:
	$(PYTHON3) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(VENV)/bin/playwright install

start:
	$(PYTHON) main.py

run:
	$(PYTHON) -c "from jobs.scrape_bsr import run; run()"

# Interactively pick which job to run on demand (scrape, digest, or both).
run-job:
	$(PYTHON) -m scripts.run_job

# Open a visible browser, auto-login (or complete OTP manually),
# then save the session to data/browser_state.json for future runs.
login:
	$(PYTHON) -c "from utils.browser import login_session; import sys; sys.exit(0 if login_session() else 1)"

# Run unit tests only (no network, no Amazon session required).
test:
	$(VENV)/bin/pytest tests/ -m "not integration" -v

# Run integration tests against live Amazon.
# Requires a valid session — run `make login` first if needed.
# Usage:
#   make test-integration                              — run all integration tests
#   make test-integration tests/integration/test_scrape_bsr_integration.py
_ITEST_ARGS := $(filter-out test-integration,$(MAKECMDGOALS))
test-integration:
	$(VENV)/bin/pytest $(if $(_ITEST_ARGS),$(_ITEST_ARGS),tests/integration/) -m integration -v -s

# Drop and re-create all tables.  Requires explicit confirmation.
#   make reset-db        — prompts error (safety guard)
#   make reset-db -- --yes  — actually resets
reset-db:
	$(PYTHON) -m scripts.reset_db --yes

COMPOSE_PROD = docker compose -f docker-compose.yml -f docker-compose.prod.yml

# Pull the latest image from GHCR and recreate the prod container with it.
# Run this on the deploy server (requires docker-compose.prod.yml's image
# path to point at the real GHCR repo, and `docker login ghcr.io` if the
# package is private).
pull-deploy:
	$(COMPOSE_PROD) pull
	$(COMPOSE_PROD) up -d
	docker image prune -f

