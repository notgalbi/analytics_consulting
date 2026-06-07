"""
kpi_engine.py — KPI calculation public interface.
Re-exports from kpi_detector for clean import paths per the system architecture.
"""
from __future__ import annotations

import pandas as pd

from utils.kpi_detector import (
    calculate_available_kpis,
    recommend_kpis,
    get_kpi_status,
    _KPI_CATALOGUE,
    _KPI_BENCHMARKS,
)


def calculate_kpis(df: pd.DataFrame, domain: str) -> dict[str, str]:
    """Calculate all computable KPIs for the given domain. Returns {name: formatted_value}."""
    return calculate_available_kpis(df, domain)


def get_recommended_kpis(df: pd.DataFrame, domain: str) -> list[dict]:
    """Return the recommended KPI list for a domain including name and description."""
    return recommend_kpis(df, domain)


def get_kpi_benchmark_status(domain: str, name: str, value: str) -> tuple[str, str]:
    """Return (emoji, note) for a KPI value vs its benchmark. Empty strings if no benchmark."""
    return get_kpi_status(domain, name, value)


def list_domain_kpis(domain: str) -> list[dict]:
    """Return the KPI catalogue entries for a domain."""
    return _KPI_CATALOGUE.get(domain, _KPI_CATALOGUE["general"])


def get_benchmark_definitions(domain: str) -> dict:
    """Return all benchmark definitions for a domain."""
    return _KPI_BENCHMARKS.get(domain, {})


__all__ = [
    "calculate_kpis",
    "get_recommended_kpis",
    "get_kpi_benchmark_status",
    "list_domain_kpis",
    "get_benchmark_definitions",
]
