"""
executive_summary.py — Executive summary generation public interface.
Re-exports from claude_summary for clean import paths per the system architecture.
"""
from __future__ import annotations

from utils.claude_summary import (
    build_safe_summary_payload,
    generate_executive_summary,
    stream_executive_summary,
    generate_kpi_narrative,
    regenerate_summary,
)


def build_payload(profile: dict, domain: str, kpis: list, pii_report: dict) -> dict:
    """Build a safe summary payload (no raw data) for Claude."""
    return build_safe_summary_payload(profile, domain, kpis, pii_report)


def generate_summary(payload: dict) -> str:
    """Generate full executive summary. Returns template if no API key."""
    return generate_executive_summary(payload)


def stream_summary(payload: dict):
    """Generator that streams the executive summary token by token."""
    return stream_executive_summary(payload)


def generate_kpi_analysis(domain: str, calc_kpis: dict, profile: dict) -> str:
    """Generate a short AI KPI narrative. Returns empty string if no API key."""
    return generate_kpi_narrative(domain, calc_kpis, profile)


def revise_summary(payload: dict, current_summary: str, instruction: str) -> str:
    """Revise an existing summary based on an admin instruction."""
    return regenerate_summary(payload, current_summary, instruction)


__all__ = [
    "build_payload",
    "generate_summary",
    "stream_summary",
    "generate_kpi_analysis",
    "revise_summary",
]
