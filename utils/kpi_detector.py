"""
kpi_detector.py — Rule-based KPI recommendation engine.

Public API:
    detect_business_domain(df)           → domain string
    recommend_kpis(df, domain)           → list of KPI definition dicts
    calculate_available_kpis(df, domain) → dict of computable KPI name → formatted value
"""
from __future__ import annotations

import pandas as pd


# ── Domain keyword scoring ────────────────────────────────────────────────────
# Each domain maps to weighted column-name fragments.
# Longer / more specific matches score higher.
_DOMAIN_SIGNALS: dict[str, list[tuple[str, int]]] = {
    "marketing": [
        ("impression", 3), ("click", 3), ("ctr", 3), ("cpc", 3),
        ("conversion", 3), ("roas", 3), ("campaign", 2), ("spend", 2),
        ("lead", 2), ("reach", 2), ("engagement", 2), ("ad", 1), ("channel", 1),
    ],
    "sales": [
        ("revenue", 3), ("order", 3), ("sale", 3), ("invoice", 2),
        ("deal", 2), ("opportunity", 2), ("quota", 2), ("customer", 1),
        ("product", 1), ("discount", 1), ("quantity", 1), ("price", 1),
    ],
    "operations": [
        ("ticket", 3), ("sla", 3), ("resolution", 3), ("backlog", 3),
        ("response_time", 3), ("throughput", 2), ("inventory", 2),
        ("shipment", 2), ("defect", 2), ("supplier", 1), ("warehouse", 1),
    ],
    "finance": [
        ("expense", 3), ("profit", 3), ("margin", 3), ("budget", 3),
        ("cost", 2), ("payment", 2), ("transaction", 2), ("balance", 2),
        ("receivable", 2), ("payable", 2), ("cash", 1), ("tax", 1),
    ],
    "hr": [
        ("employee", 3), ("attrition", 3), ("headcount", 3), ("salary", 3),
        ("department", 2), ("hire", 2), ("tenure", 2), ("performance", 2),
        ("leave", 2), ("absence", 2), ("bonus", 1), ("compensation", 1),
    ],
}

# ── KPI catalogue ─────────────────────────────────────────────────────────────
_KPI_CATALOGUE: dict[str, list[dict]] = {
    "marketing": [
        {"name": "CTR",             "formula": "clicks / impressions",        "description": "Click-through rate — engagement quality signal."},
        {"name": "CPC",             "formula": "spend / clicks",              "description": "Cost per click — efficiency of paid traffic."},
        {"name": "CPA",             "formula": "spend / conversions",         "description": "Cost per acquisition — true acquisition cost."},
        {"name": "ROAS",            "formula": "revenue / spend",             "description": "Return on ad spend — revenue generated per $ spent."},
        {"name": "Conversion Rate", "formula": "conversions / clicks",        "description": "% of clicks that resulted in a conversion."},
        {"name": "Total Spend",     "formula": "sum(spend)",                  "description": "Total media budget consumed in the period."},
        {"name": "Total Revenue",   "formula": "sum(revenue)",                "description": "Revenue attributed to marketing activity."},
    ],
    "sales": [
        {"name": "Total Revenue",     "formula": "sum(revenue)",              "description": "Sum of all revenue in the period."},
        {"name": "Avg Order Value",   "formula": "revenue / orders",          "description": "Mean revenue per order."},
        {"name": "Total Orders",      "formula": "count(order_id)",           "description": "Total order volume."},
        {"name": "Units Sold",        "formula": "sum(quantity)",             "description": "Total units moved."},
        {"name": "Revenue by Region", "formula": "groupby(region, revenue)",  "description": "Revenue breakdown by geography."},
        {"name": "Revenue by Product","formula": "groupby(product, revenue)", "description": "Revenue breakdown by product line."},
        {"name": "Avg Discount",      "formula": "mean(discount)",            "description": "Average discount rate applied."},
    ],
    "operations": [
        {"name": "Total Tickets",        "formula": "count(ticket_id)",            "description": "Volume of work items in the period."},
        {"name": "Open Tickets",         "formula": "count(status=open)",          "description": "Current backlog size."},
        {"name": "Avg Response Time",    "formula": "mean(response_time_hours)",   "description": "Mean time from ticket creation to first response."},
        {"name": "Avg Resolution Time",  "formula": "mean(resolution_time_hours)", "description": "Mean time from creation to close."},
        {"name": "Resolution Rate",      "formula": "closed / total tickets",      "description": "% of tickets resolved in the period."},
    ],
    "finance": [
        {"name": "Total Revenue",  "formula": "sum(revenue)",              "description": "Top-line revenue for the period."},
        {"name": "Total Expenses", "formula": "sum(expense)",              "description": "Total operating expenditure."},
        {"name": "Net Profit",     "formula": "revenue - expenses",        "description": "Bottom-line profitability."},
        {"name": "Margin",         "formula": "net_profit / revenue",      "description": "Net profit as a % of revenue."},
        {"name": "Budget Variance","formula": "actual - budget",           "description": "Deviation from plan."},
    ],
    "hr": [
        {"name": "Headcount",         "formula": "count(employee_id)",    "description": "Total active employees."},
        {"name": "Attrition Count",   "formula": "count(status=left)",    "description": "Employees who left in the period."},
        {"name": "Avg Salary",        "formula": "mean(salary)",          "description": "Average compensation across the workforce."},
        {"name": "Department Count",  "formula": "nunique(department)",   "description": "Number of distinct departments."},
        {"name": "Avg Tenure",        "formula": "mean(tenure)",          "description": "Mean years of service."},
    ],
    "general": [
        {"name": "Row Count",       "formula": "len(df)",                 "description": "Total records in the dataset."},
        {"name": "Completeness",    "formula": "non_null / total",        "description": "% of cells with non-null values."},
        {"name": "Unique Values",   "formula": "nunique per column",      "description": "Cardinality of key columns."},
    ],
}

# ── Column alias map for flexible matching ─────────────────────────────────────
# Maps canonical name → list of column name fragments that count as that alias.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "revenue":          ["revenue", "sales", "amount", "booking", "income", "gmv"],
    "spend":            ["spend", "cost", "ad_spend", "media_spend", "budget_used"],
    "clicks":           ["clicks", "click", "link_clicks"],
    "impressions":      ["impressions", "impression", "views", "reach"],
    "conversions":      ["conversions", "conversion", "leads", "orders_marketing"],
    "quantity":         ["quantity", "qty", "units", "volume"],
    "discount":         ["discount", "disc", "markdown"],
    "response_time_hours": ["response_time", "response_time_hours", "first_response"],
    "resolution_time_hours": ["resolution_time", "resolution_time_hours", "time_to_close"],
    "salary":           ["salary", "compensation", "pay", "wage"],
    "tenure":           ["tenure", "years_of_service", "seniority"],
}


# ── Public functions ──────────────────────────────────────────────────────────

def detect_business_domain(df: pd.DataFrame) -> str:
    """
    Score each domain by weighted keyword matches in column names.
    Returns the highest-scoring domain, or 'general' if nothing matches.
    """
    col_text = " ".join(df.columns).lower().replace(" ", "_")
    scores: dict[str, int] = {d: 0 for d in _DOMAIN_SIGNALS}

    for domain, signals in _DOMAIN_SIGNALS.items():
        for keyword, weight in signals:
            if keyword in col_text:
                scores[domain] += weight

    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "general"


def recommend_kpis(df: pd.DataFrame, domain: str) -> list[dict]:
    """
    Return the full KPI list for a domain, always appending the general KPIs.
    """
    domain_kpis = _KPI_CATALOGUE.get(domain, [])
    general_kpis = _KPI_CATALOGUE["general"] if domain != "general" else []
    return domain_kpis + general_kpis


def calculate_available_kpis(df: pd.DataFrame, domain: str) -> dict[str, str]:
    """
    Attempt to compute KPIs that can actually be derived from df's columns.
    Returns a dict of { "KPI Name": "formatted value" } for computable KPIs.
    """
    resolved = _resolve_aliases(df)
    results: dict[str, str] = {}

    calculators = {
        "marketing": _calc_marketing,
        "sales":     _calc_sales,
        "operations":_calc_operations,
        "finance":   _calc_finance,
        "hr":        _calc_hr,
    }

    calc_fn = calculators.get(domain)
    if calc_fn:
        results.update(calc_fn(df, resolved))

    return results


# ── Domain calculators ────────────────────────────────────────────────────────

def _calc_marketing(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    if r.get("spend"):
        out["Total Spend"] = _fmt_currency(df[r["spend"]].sum())
    if r.get("revenue"):
        out["Total Revenue"] = _fmt_currency(df[r["revenue"]].sum())
    if r.get("clicks") and r.get("impressions"):
        total_clicks = df[r["clicks"]].sum()
        total_impr   = df[r["impressions"]].sum()
        if total_impr > 0:
            out["CTR"] = f"{total_clicks / total_impr * 100:.2f}%"
    if r.get("spend") and r.get("clicks"):
        total_clicks = df[r["clicks"]].sum()
        total_spend  = df[r["spend"]].sum()
        if total_clicks > 0:
            out["CPC"] = _fmt_currency(total_spend / total_clicks)
    if r.get("revenue") and r.get("spend"):
        total_spend = df[r["spend"]].sum()
        if total_spend > 0:
            out["ROAS"] = f"{df[r['revenue']].sum() / total_spend:.2f}x"
    if r.get("conversions") and r.get("clicks"):
        total_clicks = df[r["clicks"]].sum()
        if total_clicks > 0:
            out["Conversion Rate"] = f"{df[r['conversions']].sum() / total_clicks * 100:.2f}%"
    return out


def _calc_sales(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    if r.get("revenue"):
        total_rev = df[r["revenue"]].sum()
        out["Total Revenue"] = _fmt_currency(total_rev)
        out["Avg Order Value"] = _fmt_currency(total_rev / len(df)) if len(df) else "$0"
    if r.get("quantity"):
        out["Units Sold"] = f"{int(df[r['quantity']].sum()):,}"
    if r.get("discount"):
        out["Avg Discount"] = f"{df[r['discount']].mean() * 100:.1f}%"
    out["Total Orders"] = f"{len(df):,}"
    return out


def _calc_operations(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    out["Total Tickets"] = f"{len(df):,}"
    if r.get("response_time_hours"):
        out["Avg Response Time"] = f"{df[r['response_time_hours']].mean():.1f} hrs"
    if r.get("resolution_time_hours"):
        out["Avg Resolution Time"] = f"{df[r['resolution_time_hours']].mean():.1f} hrs"
    # Look for a status column and count open tickets
    status_col = _find_col(df, ["status", "state"])
    if status_col:
        open_count = df[status_col].str.lower().isin(["open", "pending", "in progress"]).sum()
        out["Open Tickets"] = f"{int(open_count):,}"
    return out


def _calc_finance(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    if r.get("revenue"):
        out["Total Revenue"] = _fmt_currency(df[r["revenue"]].sum())
    spend_col = r.get("spend") or _find_col(df, ["expense", "cost", "expenses"])
    if spend_col:
        out["Total Expenses"] = _fmt_currency(df[spend_col].sum())
        if r.get("revenue"):
            net = df[r["revenue"]].sum() - df[spend_col].sum()
            out["Net Profit"] = _fmt_currency(net)
            rev = df[r["revenue"]].sum()
            if rev:
                out["Margin"] = f"{net / rev * 100:.1f}%"
    return out


def _calc_hr(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    out["Headcount"] = f"{len(df):,}"
    if r.get("salary"):
        out["Avg Salary"] = _fmt_currency(df[r["salary"]].mean())
    dept_col = _find_col(df, ["department", "dept", "team"])
    if dept_col:
        out["Department Count"] = f"{df[dept_col].nunique():,}"
    if r.get("tenure"):
        out["Avg Tenure"] = f"{df[r['tenure']].mean():.1f} yrs"
    return out


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_aliases(df: pd.DataFrame) -> dict[str, str]:
    """Map canonical alias names → actual column names found in df."""
    col_lower = {c.lower().replace(" ", "_"): c for c in df.columns}
    resolved = {}
    for canonical, fragments in _COLUMN_ALIASES.items():
        for frag in fragments:
            matched = next((col_lower[k] for k in col_lower if frag in k), None)
            if matched and pd.api.types.is_numeric_dtype(df[matched]):
                resolved[canonical] = matched
                break
    return resolved


def _find_col(df: pd.DataFrame, fragments: list[str]) -> str | None:
    """Return the first column name containing any of the given fragments."""
    for col in df.columns:
        col_l = col.lower()
        if any(f in col_l for f in fragments):
            return col
    return None


def _fmt_currency(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    if abs(val) >= 1_000:
        return f"${val / 1_000:.1f}K"
    return f"${val:,.2f}"
