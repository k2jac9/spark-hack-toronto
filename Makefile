.PHONY: install data serve cli test fmt

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
