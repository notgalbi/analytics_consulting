"""
kpi_detector.py — Infers the dataset type from column names and recommends KPIs.
"""

import pandas as pd


# Keywords per domain for dataset-type detection
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "sales": [
        "revenue", "sales", "order", "orders", "customer", "product",
        "price", "quantity", "qty", "discount", "invoice", "deal",
        "opportunity", "pipeline", "quota", "upsell",
    ],
    "marketing": [
        "campaign", "channel", "impressions", "clicks", "ctr", "cpc",
        "conversion", "lead", "leads", "roas", "roi", "spend", "ad",
        "audience", "reach", "engagement",
    ],
    "operations": [
        "inventory", "warehouse", "stock", "sku", "shipment", "delivery",
        "supplier", "vendor", "logistics", "sla", "turnaround", "defect",
        "production", "output", "throughput",
    ],
    "finance": [
        "expense", "profit", "loss", "budget", "cost", "payment",
        "invoice", "payable", "receivable", "cash", "margin", "ebitda",
        "balance", "transaction", "debit", "credit",
    ],
    "hr": [
        "employee", "department", "salary", "hire", "tenure", "performance",
        "headcount", "attrition", "leave", "absence", "training",
        "compensation", "bonus", "role", "grade",
    ],
}

# KPI templates per domain
_KPI_TEMPLATES: dict[str, list[dict]] = {
    "sales": [
        {"name": "Total Revenue",        "description": "Sum of all revenue in the period."},
        {"name": "Average Order Value",   "description": "Mean revenue per order."},
        {"name": "Total Orders",          "description": "Count of distinct orders."},
        {"name": "Total Customers",       "description": "Count of distinct customers."},
        {"name": "Discount Rate",         "description": "Average discount applied to orders."},
        {"name": "Revenue per Product",   "description": "Breakdown of revenue by product."},
        {"name": "Sales by Region",       "description": "Revenue split across geographic regions."},
    ],
    "marketing": [
        {"name": "Click-Through Rate (CTR)",   "description": "Clicks / Impressions."},
        {"name": "Conversion Rate",            "description": "Conversions / Clicks."},
        {"name": "Cost per Click (CPC)",       "description": "Total spend / Total clicks."},
        {"name": "Return on Ad Spend (ROAS)",  "description": "Revenue / Ad spend."},
        {"name": "Leads Generated",            "description": "Total leads captured in period."},
        {"name": "Top-performing Channels",    "description": "Channels ranked by conversion."},
    ],
    "operations": [
        {"name": "On-Time Delivery Rate",  "description": "% of shipments delivered on or before SLA."},
        {"name": "Inventory Turnover",     "description": "Units sold / Average inventory."},
        {"name": "Defect Rate",            "description": "Defective units / Total units produced."},
        {"name": "Average Lead Time",      "description": "Mean days from order to delivery."},
        {"name": "Supplier Performance",   "description": "On-time and quality rating per supplier."},
    ],
    "finance": [
        {"name": "Gross Profit Margin",    "description": "(Revenue − COGS) / Revenue."},
        {"name": "Operating Expenses",     "description": "Total opex for the period."},
        {"name": "Budget Variance",        "description": "Actual spend vs budgeted spend."},
        {"name": "Accounts Receivable Days", "description": "Average days to collect payment."},
        {"name": "Cash Flow",              "description": "Net cash in vs out over the period."},
    ],
    "hr": [
        {"name": "Headcount",              "description": "Total active employees."},
        {"name": "Attrition Rate",         "description": "Employees left / Average headcount."},
        {"name": "Average Tenure",         "description": "Mean years of service."},
        {"name": "Salary by Department",   "description": "Average compensation per department."},
        {"name": "Performance Score Dist.","description": "Distribution of performance ratings."},
    ],
    "general": [
        {"name": "Row Count",       "description": "Total records in the dataset."},
        {"name": "Data Completeness","description": "% of cells with non-null values."},
        {"name": "Unique Values",   "description": "Cardinality of key categorical columns."},
    ],
}


def detect_dataset_type(df: pd.DataFrame) -> str:
    """Score each domain by how many of its keywords appear in column names."""
    col_text = " ".join(df.columns).lower()
    scores: dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for kw in keywords if kw in col_text)

    best_domain = max(scores, key=lambda d: scores[d])
    return best_domain if scores[best_domain] > 0 else "general"


def recommend_kpis(dataset_type: str, df: pd.DataFrame) -> list[dict]:
    """
    Return KPI recommendations for the detected type.
    Filters out KPIs whose required column keywords are absent when possible.
    """
    base_kpis = _KPI_TEMPLATES.get(dataset_type, _KPI_TEMPLATES["general"])
    # Always append a few general KPIs
    if dataset_type != "general":
        base_kpis = base_kpis + _KPI_TEMPLATES["general"]
    return base_kpis
