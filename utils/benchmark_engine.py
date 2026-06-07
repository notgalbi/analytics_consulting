"""
benchmark_engine.py — Benchmark comparison public interface.
Re-exports benchmark data and comparison logic from kpi_detector.
"""
from __future__ import annotations

import re

from utils.kpi_detector import get_kpi_status, _KPI_BENCHMARKS


def compare_to_benchmark(domain: str, kpi_name: str, value: str) -> dict:
    """
    Compare a KPI value to its industry benchmark.

    Returns dict with:
    - status: "above_benchmark" | "at_benchmark" | "below_benchmark" | "no_benchmark"
    - emoji: str
    - note: str
    - direction: "higher_is_better" | "lower_is_better" | None
    """
    emoji, note = get_kpi_status(domain, kpi_name, value)
    bench = _KPI_BENCHMARKS.get(domain, {}).get(kpi_name)

    if not bench:
        return {"status": "no_benchmark", "emoji": "", "note": "", "direction": None}

    v = value.strip()
    if v.startswith("$"):
        return {"status": "no_benchmark", "emoji": "", "note": note, "direction": None}
    if " / " in v:
        v = v.split(" / ")[0]
    m = re.search(r"([+-]?\d+(?:\.\d+)?)", v)
    if not m:
        return {"status": "no_benchmark", "emoji": emoji, "note": note, "direction": None}

    val = float(m.group(1))
    direction = bench["direction"]
    good, warn = bench["good"], bench["warn"]

    if direction == "higher":
        status = "above_benchmark" if val >= good else ("at_benchmark" if val >= warn else "below_benchmark")
    else:
        status = "above_benchmark" if val <= good else ("at_benchmark" if val <= warn else "below_benchmark")

    return {
        "status": status,
        "emoji": emoji,
        "note": note,
        "direction": "higher_is_better" if direction == "higher" else "lower_is_better",
    }


def get_all_benchmarks(domain: str) -> dict:
    """Return all benchmark definitions for a domain."""
    return _KPI_BENCHMARKS.get(domain, {})


def get_benchmark_violations(domain: str, calc_kpis: dict[str, str]) -> list[dict]:
    """
    Return KPIs that are below benchmark for the domain.
    Each item: {name, value, status, note, severity}
    """
    violations = []
    for name, value in calc_kpis.items():
        result = compare_to_benchmark(domain, name, value)
        if result["status"] == "below_benchmark":
            violations.append({
                "name": name,
                "value": value,
                "status": result["status"],
                "note": result["note"],
                "severity": "high" if result["emoji"] == "🔴" else "medium",
            })
    return violations


__all__ = ["compare_to_benchmark", "get_all_benchmarks", "get_benchmark_violations"]
