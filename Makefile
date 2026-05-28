.PHONY: install data serve cli test demo demo-cli demo-data

# demo  -> real downtown-Toronto slice (demo_data/), pins land on the offline map.
# demo-cli/tests -> synthetic, deterministic fixtures/.
DEMO_DATA ?= demo_data
FIXTURES ?= fixtures

install:
	pip install -r requirements.txt

data:
	python scripts/download_data.py

serve:
	uvicorn civic_analyst.api.server:app --reload --port 8000 --app-dir src

cli:
	python -m civic_analyst.cli analyze "100 Queen St W"

test:
	PYTHONPATH=src pytest -q

# One-command demo: serve the API + offline map against REAL downtown Toronto data.
demo:
	@echo "Serving REAL downtown Toronto data (demo_data/). Once up:"
	@echo "  open http://localhost:8000/                 # offline map, real establishments"
	@echo "  curl 'http://localhost:8000/health'"
	DATA_DIR=$(DEMO_DATA) uvicorn civic_analyst.api.server:app --port 8000 --app-dir src

# Rebuild the real downtown slice from the live dataset.
demo-data:
	PYTHONPATH=src python scripts/build_demo_slice.py

# Quick deterministic check (synthetic fixtures): prints a populated report and exits.
demo-cli:
	DATA_DIR=$(FIXTURES) PYTHONPATH=src python -m civic_analyst.cli analyze "100 Queen St W"
