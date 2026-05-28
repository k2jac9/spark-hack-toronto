"""Build a knowledge graph linking addresses, premises, permits and inspections.

Nodes are typed (address / business / permit / inspection / request). Edges connect
a record to the address it occurred at, so a query for an address can traverse to
every related signal — the structure that won the NYC edition.
"""
from __future__ import annotations

import re

import networkx as nx


def normalize_address(raw: str) -> str:
    """Cheap address key. The real entity-resolution (fuzzy matching across
    messy municipal address formats) is the local-LLM job — see agents/subagents."""
    s = raw.upper().strip()
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\bSTREET\b", "ST", s)
    s = re.sub(r"\bAVENUE\b", "AVE", s)
    s = re.sub(r"\bWEST\b", "W", s)
    s = re.sub(r"\bEAST\b", "E", s)
    return re.sub(r"\s+", " ", s).strip()


class CivicGraph:
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()

    def add_address(self, raw_address: str) -> str:
        key = normalize_address(raw_address)
        node = f"address:{key}"
        if node not in self.g:
            self.g.add_node(node, kind="address", label=raw_address)
        return node

    def add_record(self, kind: str, record_id: str, address: str, **attrs: object) -> str:
        """Attach a typed record (permit/inspection/request/...) to its address."""
        node = f"{kind}:{record_id}"
        self.g.add_node(node, kind=kind, **attrs)
        addr_node = self.add_address(address)
        self.g.add_edge(addr_node, node, kind="has_" + kind)
        return node

    def records_for(self, raw_address: str, kind: str | None = None) -> list[dict]:
        addr_node = f"address:{normalize_address(raw_address)}"
        if addr_node not in self.g:
            return []
        out = []
        for _, target, data in self.g.out_edges(addr_node, data=True):
            node_data = self.g.nodes[target]
            if kind is None or node_data.get("kind") == kind:
                out.append({"id": target, **node_data})
        return out

    def __len__(self) -> int:
        return self.g.number_of_nodes()
