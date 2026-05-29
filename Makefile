.PHONY: install install-hooks data serve cli test demo demo-cli demo-data

# demo  -> real downtown-Toronto slice (demo_data/), pins land on the offline map.
# demo-cli/tests -> synthetic, deterministic fixtures/.
DEMO_DATA ?= demo_data
FIXTURES ?= fixtures

# Prefer the project venv if present, so `make test` works whether or not the
# venv is activated in the current shell. Override with `make PYTHON=...`.
PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)

install:
	$(PYTHON) -m pip install -r requirements.txt

# Run once per clone (you AND your teammate). Enables the shared pre-push hook
# that blocks pushing a red test suite. Bypass an emergency push with --no-verify.
install-hooks:
	chmod +x scripts/hooks/*
	git config core.hooksPath scripts/hooks
	@echo "Pre-push hook enabled (core.hooksPath=scripts/hooks)."

data:
	$(PYTHON) scripts/download_data.py

serve:
	$(PYTHON) -m uvicorn civic_analyst.api.server:app --reload --port 8000 --app-dir src

cli:
	$(PYTHON) -m civic_analyst.cli analyze "100 Queen St W"

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

# One-command demo: serve the API + offline map against REAL downtown Toronto data.
demo:
	@echo "Serving REAL downtown Toronto data (demo_data/). Once up:"
	@echo "  open http://localhost:8000/                 # offline map, real establishments"
	@echo "  curl 'http://localhost:8000/health'"
	DATA_DIR=$(DEMO_DATA) $(PYTHON) -m uvicorn civic_analyst.api.server:app --port 8000 --app-dir src

# Rebuild the real downtown slice from the live dataset.
demo-data:
	PYTHONPATH=src $(PYTHON) scripts/build_demo_slice.py

# Quick deterministic check (synthetic fixtures): prints a populated report and exits.
demo-cli:
	DATA_DIR=$(FIXTURES) PYTHONPATH=src $(PYTHON) -m civic_analyst.cli analyze "100 Queen St W"
