"""FastAPI surface for the demo: GET /analyze?address=...

The knowledge graph is built once at startup from the pre-downloaded datasets
(scripts/download_data.py → DATA_DIR). If no data is present the graph stays empty
and the server still boots, so the API is safe to run offline.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

from ..agents.supervisor import Supervisor
from ..config import settings
from ..graph.builder import CivicGraph
from ..ingest.loader import load_into_graph

_graph = CivicGraph()
_supervisor = Supervisor(_graph)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.load_summary = load_into_graph(_graph, settings.data_dir)
    yield


app = FastAPI(title="Toronto Civic Risk Analyst", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "graph_nodes": len(_graph),
        "loaded": getattr(app.state, "load_summary", {}),
    }


@app.get("/analyze")
def analyze(address: str = Query(..., min_length=3, max_length=200)) -> dict:
    return _supervisor.analyze(address).to_dict()
