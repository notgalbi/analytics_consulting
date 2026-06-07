"""
semantic_layer.py — Industry context loader.

Reads config/industry_templates.yaml and returns structured context for a domain.
Falls back to built-in defaults if the YAML file is unavailable.

Public API:
    get_industry_context(domain) -> dict
    list_supported_domains() -> list[str]
"""
from __future__ import annotations

from pathlib import Path

_TEMPLATES_PATH = Path(__file__).parent.parent / "config" / "industry_templates.yaml"

# ── Minimal fallback used when YAML is missing ────────────────────────────────
_FALLBACK: dict[str, dict] = {
    "general": {
        "display_name": "General Business",
        "executive_objectives": ["Understand data structure and quality", "Identify key metrics and trends"],
        "critical_kpis": [],
        "value_drivers": ["Data completeness", "Metric accuracy"],
        "risk_indicators": ["High missing value rate", "Duplicate records"],
        "recommended_actions": ["Improve data quality before analysis"],
        "financial_levers": [],
        "common_report_sections": ["Data Overview", "Quality Report", "Key Metrics"],
    }
}


def _load_templates() -> dict:
    """Load industry templates from YAML, returning fallback on failure."""
    try:
        import yaml
        if _TEMPLATES_PATH.exists():
            with open(_TEMPLATES_PATH, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return _FALLBACK


_EMPTY_TEMPLATE: dict = {
    "display_name": "",
    "executive_objectives": [],
    "critical_kpis": [],
    "value_drivers": [],
    "risk_indicators": [],
    "recommended_actions": [],
    "financial_levers": [],
    "common_report_sections": [],
}


def get_industry_context(domain: str) -> dict:
    """
    Return the industry template for a given domain.
    Falls back to 'general' if domain not found, then to hardcoded fallback.
    """
    templates = _load_templates()
    context = templates.get(domain) or templates.get("general") or _FALLBACK["general"]

    # Ensure all expected keys are present
    result = dict(_EMPTY_TEMPLATE)
    result.update(context)
    return result


def list_supported_domains() -> list[str]:
    """Return all domain keys from the templates file."""
    templates = _load_templates()
    return list(templates.keys())


__all__ = ["get_industry_context", "list_supported_domains"]
