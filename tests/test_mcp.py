"""Test the MCP tool logic directly (no MCP runtime needed)."""
from pathlib import Path

import pytest

from civic_analyst import mcp_server
from civic_analyst.graph.builder import normalize_address

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def test_list_datasets_includes_permits():
    keys = {d["key"] for d in mcp_server.list_datasets()}
    assert {"permits", "dinesafe", "311", "licences"} <= keys


def test_tools_operate_on_loaded_graph():
    summary = mcp_server.load(FIXTURES)
    assert summary["dinesafe"] == 4

    ranked = mcp_server.top_risk(limit=3)
    assert normalize_address(ranked[0]["address"]) == normalize_address("100 Queen St W")
    assert ranked[0]["risk_score"] == 0.826

    report = mcp_server.analyze_address("100 Queen St W")
    assert report["risk_score"] == 0.826 and report["found"] is True


def test_build_server_registers_expected_tools():
    """The MCP server exposes the analyst's capabilities as named tools."""
    pytest.importorskip("mcp", reason="mcp runtime not installed")
    server = mcp_server.build_server()
    # FastMCP keeps a tool registry we can introspect without a live transport.
    names = {t.name for t in server._tool_manager.list_tools()}
    assert {
        "list_datasets",
        "dataset_resources",
        "analyze_address",
        "top_risk",
        "city_digest",
    } <= names


def test_city_digest_is_offline_safe():
    """No model reachable -> deterministic briefing, never a crash."""
    mcp_server.load(FIXTURES)
    briefing = mcp_server.city_digest(limit=5)
    assert isinstance(briefing, str) and briefing.strip()


def test_analyze_address_rejects_blank():
    """Malformed arg is rejected at the boundary with a clear error."""
    for bad in ("", "   ", None, 123):
        with pytest.raises(ValueError):
            mcp_server.analyze_address(bad)  # type: ignore[arg-type]


def test_top_risk_validates_and_clamps_limit():
    mcp_server.load(FIXTURES)
    # bad types / values rejected
    for bad in (0, -1, "5", True):
        with pytest.raises(ValueError):
            mcp_server.top_risk(limit=bad)  # type: ignore[arg-type]
    # absurdly large limit is clamped, not honored
    ranked = mcp_server.top_risk(limit=10_000)
    assert len(ranked) <= mcp_server.MAX_LIMIT


def test_dataset_resources_rejects_unknown_key():
    with pytest.raises(ValueError):
        mcp_server.dataset_resources("not-a-real-dataset")
