"""
domain_detector.py — Domain detection public interface.
Re-exports from kpi_detector for clean import paths per the system architecture.
"""
from __future__ import annotations

import pandas as pd

from utils.kpi_detector import detect_business_domain, _DOMAIN_SIGNALS


def detect_domain(df: pd.DataFrame) -> str:
    """Detect business domain from DataFrame column names. Returns domain string."""
    return detect_business_domain(df)


def detect_domain_with_confidence(df: pd.DataFrame) -> dict:
    """
    Returns domain detection result with confidence score and evidence.

    Returns dict with:
    - domain: str
    - confidence: float (0.0–1.0)
    - evidence: list[str] — column signals that triggered detection
    - scores: dict[str, int] — all domain scores
    """
    col_text = " ".join(df.columns).lower().replace(" ", "_")
    scores: dict[str, int] = {d: 0 for d in _DOMAIN_SIGNALS}

    for domain, signals in _DOMAIN_SIGNALS.items():
        for keyword, weight in signals:
            if keyword in col_text:
                scores[domain] += weight

    best = max(scores, key=lambda d: scores[d])
    best_score = scores[best]
    detected = best if best_score > 0 else "general"

    total_possible = sum(w for _, w in _DOMAIN_SIGNALS.get(detected, []))
    confidence = min(best_score / max(total_possible, 1), 1.0) if best_score > 0 else 0.0

    evidence = [
        f"Column signal '{kw}' (weight {w})"
        for kw, w in _DOMAIN_SIGNALS.get(detected, [])
        if kw in col_text
    ]

    return {
        "domain": detected,
        "confidence": round(confidence, 2),
        "evidence": evidence[:5],
        "scores": scores,
    }


__all__ = ["detect_domain", "detect_domain_with_confidence"]
