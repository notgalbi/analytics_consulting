"""
storage.py — Local MVP storage for processed dashboard outputs.

Each dashboard is stored under outputs/{dashboard_id}/ as:
    metadata.json   — file info, domain, PII report, delivery status
    profile.json    — data quality profile
    kpis.json       — recommended + calculated KPIs
    summary.txt     — executive summary text
    charts.json     — serialised Plotly figures
    sanitized.csv   — sanitized DataFrame (written by caller if needed)

Dashboard IDs follow the pattern:  dashboard_YYYYMMDD_xxxxxx

Public API:
    create_dashboard_id()                                                → str
    save_processed_output(dashboard_id, profile, kpis,
                          charts_metadata, summary, extra)               → Path
    load_processed_output(dashboard_id)                                  → dict | None
    list_saved_dashboards()                                              → list[dict]
    delete_dashboard(dashboard_id)                                       → bool
    update_delivery_status(dashboard_id, status, notes)                  → bool
"""
from __future__ import annotations

import json
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"

# Valid delivery statuses
STATUSES = ("Needs Review", "Approved", "Delivered")


# ── Public functions ──────────────────────────────────────────────────────────

def create_dashboard_id() -> str:
    """Return a human-readable dashboard ID like dashboard_20260530_ab12cd."""
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid_part  = uuid.uuid4().hex[:6]
    return f"dashboard_{date_part}_{uid_part}"


def save_processed_output(
    dashboard_id: str,
    profile: dict,
    kpis: dict,
    charts_metadata: dict,
    summary: str,
    extra: dict | None = None,
) -> Path:
    """
    Persist all processed outputs for a dashboard.
    `extra` may contain: metadata, pii_report, domain, figures (Plotly JSON), sanitized_csv.
    Returns the directory path.
    """
    out_dir = _OUTPUTS_DIR / dashboard_id
    out_dir.mkdir(parents=True, exist_ok=True)

    extra = extra or {}

    # metadata.json — lightweight index entry
    metadata = {
        "dashboard_id":    dashboard_id,
        "created_at":      datetime.now(timezone.utc).isoformat(),
        "delivery_status": "Needs Review",
        "review_notes":    "",
        "domain":          extra.get("domain", "general"),
        "filename":        extra.get("metadata", {}).get("filename", "Unknown"),
        "row_count":       profile.get("row_count"),
        "col_count":       profile.get("col_count"),
        "pii_risk_level":  extra.get("pii_report", {}).get("risk_level", "none"),
        "pii_column_count":extra.get("pii_report", {}).get("total_pii_columns", 0),
        "file_metadata":   extra.get("metadata", {}),
        "pii_report":      extra.get("pii_report", {}),
    }
    _write_json(out_dir / "metadata.json", metadata)

    # profile.json
    _write_json(out_dir / "profile.json", _serialise(profile))

    # kpis.json
    _write_json(out_dir / "kpis.json", _serialise(kpis))

    # summary.txt
    (out_dir / "summary.txt").write_text(summary, encoding="utf-8")

    # charts.json — Plotly figure JSON strings keyed by chart title
    figures_json = extra.get("figures", {})
    _write_json(out_dir / "charts.json", figures_json)

    # sanitized.csv — optional
    sanitized_csv = extra.get("sanitized_csv")
    if sanitized_csv:
        (out_dir / "sanitized.csv").write_text(sanitized_csv, encoding="utf-8")

    return out_dir


def load_processed_output(dashboard_id: str) -> dict | None:
    """
    Load all persisted files for a dashboard into a single dict.
    Returns None if the dashboard directory or metadata file is missing.
    """
    out_dir = _OUTPUTS_DIR / dashboard_id
    metadata_path = out_dir / "metadata.json"
    if not metadata_path.exists():
        return None

    result = {
        "metadata": _read_json(metadata_path),
        "profile":  _read_json(out_dir / "profile.json"),
        "kpis":     _read_json(out_dir / "kpis.json"),
        "summary":  _read_text(out_dir / "summary.txt"),
        "charts":   _read_json(out_dir / "charts.json"),
    }
    # Merge top-level metadata fields for convenience
    result.update(result["metadata"])
    return result


def list_saved_dashboards() -> list[dict]:
    """
    Return a list of lightweight index dicts for all saved dashboards,
    sorted newest first.
    """
    if not _OUTPUTS_DIR.exists():
        return []

    results = []
    for entry in sorted(_OUTPUTS_DIR.iterdir(), reverse=True):
        meta_path = entry / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = _read_json(meta_path)
            results.append({
                "dashboard_id":    meta.get("dashboard_id", entry.name),
                "filename":        meta.get("filename", "Unknown"),
                "created_at":      meta.get("created_at", ""),
                "delivery_status": meta.get("delivery_status", "Needs Review"),
                "domain":          meta.get("domain", "general"),
                "row_count":       meta.get("row_count"),
                "pii_risk_level":  meta.get("pii_risk_level", "none"),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return results


def delete_dashboard(dashboard_id: str) -> bool:
    """Permanently delete a dashboard directory. Returns True on success."""
    out_dir = _OUTPUTS_DIR / dashboard_id
    if not out_dir.exists():
        return False
    shutil.rmtree(out_dir)
    return True


def update_delivery_status(dashboard_id: str, status: str, notes: str = "") -> bool:
    """
    Update delivery_status and review_notes in metadata.json.
    Status must be one of: 'Needs Review', 'Approved', 'Delivered'.
    """
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")

    meta_path = _OUTPUTS_DIR / dashboard_id / "metadata.json"
    if not meta_path.exists():
        return False

    meta = _read_json(meta_path)
    meta["delivery_status"] = status
    meta["review_notes"]    = notes
    _write_json(meta_path, meta)
    return True


def update_summary(dashboard_id: str, summary: str) -> bool:
    """Overwrite summary.txt with an edited or Claude-revised version."""
    path = _OUTPUTS_DIR / dashboard_id / "summary.txt"
    if not path.parent.exists():
        return False
    path.write_text(summary, encoding="utf-8")
    return True


def update_approved_charts(dashboard_id: str, approved_charts: list[str]) -> bool:
    """
    Persist the admin-selected chart titles to metadata.json.
    The client dashboard uses this list to filter which charts are shown.
    An empty list means all charts are hidden; None (key absent) means show all.
    """
    meta_path = _OUTPUTS_DIR / dashboard_id / "metadata.json"
    if not meta_path.exists():
        return False
    meta = _read_json(meta_path)
    meta["approved_charts"] = approved_charts
    _write_json(meta_path, meta)
    return True


# ── Internal helpers ──────────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _serialise(obj):
    """Recursively convert numpy/pandas scalars to JSON-native Python types."""
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(v) for v in obj]
    if hasattr(obj, "item"):   # numpy scalar
        return obj.item()
    return obj
