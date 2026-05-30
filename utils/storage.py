"""
storage.py — Saves and loads dashboard outputs to the local filesystem.
Each dashboard is stored in outputs/{dashboard_id}/ as:
  - dashboard.json   (metadata, stats, summary, chart specs)
  - sanitized_data.csv
"""
from __future__ import annotations

import json
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.io as pio
import plotly.graph_objects as go


_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


def new_dashboard_id() -> str:
    return uuid.uuid4().hex[:12]


def save_dashboard(
    dashboard_id: str,
    metadata: dict,
    profile: dict,
    pii_detections: list[dict],
    dataset_type: str,
    kpis: list[dict],
    summary: str,
    figures: dict[str, go.Figure],
    sanitized_df: pd.DataFrame,
) -> Path:
    """
    Persist the full dashboard to disk.
    Returns the directory path where it was saved.
    """
    output_dir = _OUTPUTS_DIR / dashboard_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Serialise Plotly figures to JSON strings
    charts_json = {title: pio.to_json(fig) for title, fig in figures.items()}

    payload = {
        "dashboard_id": dashboard_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending",
        "review_notes": "",
        "metadata": metadata,
        "profile": _serialise(profile),
        "pii_detections": pii_detections,
        "dataset_type": dataset_type,
        "kpis": kpis,
        "summary": summary,
        "charts": charts_json,
    }

    with open(output_dir / "dashboard.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    sanitized_df.to_csv(output_dir / "sanitized_data.csv", index=False)

    return output_dir


def load_dashboard(dashboard_id: str) -> dict | None:
    """Load a saved dashboard by ID. Returns None if not found."""
    path = _OUTPUTS_DIR / dashboard_id / "dashboard.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_sanitized_csv(dashboard_id: str) -> pd.DataFrame | None:
    """Load the sanitized CSV for a dashboard. Returns None if not found."""
    path = _OUTPUTS_DIR / dashboard_id / "sanitized_data.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def list_dashboards() -> list[dict]:
    """Return a list of dashboard summary dicts, sorted newest first."""
    results = []
    if not _OUTPUTS_DIR.exists():
        return results
    for entry in sorted(_OUTPUTS_DIR.iterdir(), reverse=True):
        json_path = entry / "dashboard.json"
        if json_path.exists():
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "dashboard_id": data.get("dashboard_id"),
                    "filename":     data.get("metadata", {}).get("filename", "Unknown"),
                    "created_at":   data.get("created_at"),
                    "review_status": data.get("review_status", "pending"),
                    "dataset_type": data.get("dataset_type", "general"),
                    "row_count":    data.get("profile", {}).get("row_count"),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return results


def update_review(dashboard_id: str, status: str, notes: str) -> bool:
    """Update the review_status and review_notes for a dashboard."""
    path = _OUTPUTS_DIR / dashboard_id / "dashboard.json"
    if not path.exists():
        return False
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["review_status"] = status
    data["review_notes"] = notes
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return True


def restore_figures(charts_json: dict) -> dict[str, go.Figure]:
    """Deserialise stored Plotly JSON back into Figure objects."""
    return {title: pio.from_json(spec) for title, spec in charts_json.items()}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialise(obj):
    """Recursively convert non-JSON-native types (int64, etc.) to Python natives."""
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(v) for v in obj]
    if hasattr(obj, "item"):          # numpy scalar
        return obj.item()
    return obj
