.PHONY: install start run login

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

# Open a visible browser, auto-login (or complete OTP manually),
# then save the session to data/browser_state.json for future runs.
login:
	$(PYTHON) -c "from utils.browser import login_session; import sys; sys.exit(0 if login_session() else 1)"
