"""FastAPI surface for the demo: GET /analyze?address=...

The graph is built once at startup. For the hackathon, load it from pre-downloaded
data (see scripts/download_data.py); here it starts empty and is populated by the
loader so the server boots even offline.
"""
from __future__ import annotations

from fastapi import FastAPI, Query

from ..agents.supervisor import Supervisor
from ..graph.builder import CivicGraph

app = FastAPI(title="Toronto Civic Risk Analyst", version="0.1.0")

# Single in-memory graph for the demo. Replace with the loader in scripts/.
_graph = CivicGraph()
_supervisor = Supervisor(_graph)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "graph_nodes": len(_graph)}


@app.get("/analyze")
def analyze(address: str = Query(..., min_length=3, max_length=200)) -> dict:
    return _supervisor.analyze(address).to_dict()
