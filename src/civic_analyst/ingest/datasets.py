"""Registry of the City of Toronto open datasets this project fuses.

Slugs verified against open.toronto.ca. Freshness notes drive which we lean on:
permits + DineSafe are daily/frequent and address-level; 311 is monthly and
ward-level only; business licences enrich the entity graph.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dataset:
    slug: str            # CKAN package id on open.toronto.ca
    title: str
    cadence: str         # update frequency
    geo: str             # finest geography available
    notes: str


REGISTRY: dict[str, Dataset] = {
    "permits": Dataset(
        slug="building-permits-active-permits",
        title="Building Permits — Active Permits",
        cadence="daily",
        geo="address",
        notes="Includes review/inspection stages; freshest, richest signal.",
    ),
    "permits_cleared": Dataset(
        slug="building-permits-cleared-permits",
        title="Building Permits — Cleared Permits",
        cadence="daily",
        geo="address",
        notes="Historical closures; pairs with active for the permit lifecycle.",
    ),
    "dinesafe": Dataset(
        slug="dinesafe",
        title="DineSafe — Food Premises Inspections",
        cadence="daily",
        geo="address",
        notes="Real inspection outcomes/infractions — strong safety-risk signal.",
    ),
    "311": Dataset(
        slug="311-service-requests-customer-initiated",
        title="311 Service Requests (Customer Initiated)",
        cadence="monthly",
        geo="ward / intersection / FSA",
        notes="No lat/long; ~30-35% coverage, 6 of 45 divisions. Use as area signal.",
    ),
    "licences": Dataset(
        slug="municipal-licensing-and-standards-business-licences-and-permits",
        title="Business Licences & Permits",
        cadence="daily",
        geo="address",
        notes="Ties a premises to an operator entity for the knowledge graph.",
    ),
}


def get(name: str) -> Dataset:
    if name not in REGISTRY:
        raise KeyError(f"unknown dataset {name!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[name]
