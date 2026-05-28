.PHONY: install data serve cli test demo demo-cli

# Synthetic data shipped in fixtures/ — lets the team demo a populated /analyze
# with zero downloads.
DEMO_DATA ?= fixtures

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

# One-command demo: serve the API against the synthetic fixtures.
demo:
	@echo "Serving with synthetic fixtures (fixtures/). Once up, try:"
	@echo "  curl 'http://localhost:8000/health'"
	@echo "  curl 'http://localhost:8000/analyze?address=100%20Queen%20St%20W'  # high risk"
	@echo "  curl 'http://localhost:8000/analyze?address=55%20John%20St'        # low risk"
	DATA_DIR=$(DEMO_DATA) uvicorn civic_analyst.api.server:app --port 8000 --app-dir src

# Quick non-server demo: print a populated report and exit.
demo-cli:
	DATA_DIR=$(DEMO_DATA) PYTHONPATH=src python -m civic_analyst.cli analyze "100 Queen St W"
