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
# Ecommerce/retail/saas use higher weights so their specific signals dominate.
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
        ("response_time", 3), ("throughput", 2), ("shipment", 2),
        ("defect", 2), ("warehouse", 1),
    ],
    "finance": [
        ("expense", 3), ("profit", 3), ("budget", 3),
        ("payment", 2), ("transaction", 2), ("balance", 2),
        ("receivable", 2), ("payable", 2), ("cash", 1), ("tax", 1),
    ],
    "hr": [
        ("employee", 3), ("attrition", 3), ("headcount", 3), ("salary", 3),
        ("department", 2), ("hire", 2), ("tenure", 2), ("performance", 2),
        ("leave", 2), ("absence", 2), ("bonus", 1), ("compensation", 1),
    ],
    "saas": [
        ("mrr", 6), ("arr", 5), ("nps_score", 6), ("nps", 4), ("churn", 5),
        ("subscription", 4), ("plan_type", 5), ("seats", 4), ("ltv", 5),
        ("arpu", 5), ("recurring", 4), ("contract_month", 4),
        ("support_ticket", 3), ("acquisition_channel", 4), ("trial", 3),
    ],
    "ecommerce": [
        ("return_flag", 7), ("days_to_ship", 6), ("discount_pct", 4),
        ("checkout", 5), ("cart", 4), ("sku", 5), ("fulfillment", 4),
        ("refund", 4), ("tracking", 3),
    ],
    "retail": [
        ("units_in_stock", 7), ("reorder_point", 7), ("stockout", 6),
        ("units_sold_30d", 6), ("days_since_restock", 6), ("inventory_status", 5),
        ("cost_price", 5), ("sell_price", 5), ("margin_pct", 5),
        ("restock", 4), ("supplier", 2),
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
        {"name": "Total Revenue",       "formula": "sum(revenue)",              "description": "Sum of all revenue in the period."},
        {"name": "Avg Order Value",     "formula": "revenue / orders",          "description": "Mean revenue per order."},
        {"name": "Total Orders",        "formula": "count(order_id)",           "description": "Total order volume."},
        {"name": "Units Sold",          "formula": "sum(quantity)",             "description": "Total units moved."},
        {"name": "Avg Discount",        "formula": "mean(discount)",            "description": "Average discount rate applied."},
        {"name": "MoM Revenue Growth",  "formula": "last_month / prev_month",   "description": "Month-over-month revenue growth rate."},
        {"name": "Revenue by Region",   "formula": "groupby(region, revenue)",  "description": "Revenue breakdown by geography."},
        {"name": "Revenue by Category", "formula": "groupby(category, revenue)","description": "Revenue breakdown by product category."},
    ],
    "operations": [
        {"name": "Total Tickets",       "formula": "count(ticket_id)",            "description": "Volume of work items in the period."},
        {"name": "Open Tickets",        "formula": "count(status=open)",          "description": "Current backlog size."},
        {"name": "Avg Response Time",   "formula": "mean(response_time_hours)",   "description": "Mean time from ticket creation to first response."},
        {"name": "Avg Resolution Time", "formula": "mean(resolution_time_hours)", "description": "Mean time from creation to close."},
        {"name": "Resolution Rate",     "formula": "closed / total tickets",      "description": "% of tickets resolved in the period."},
    ],
    "finance": [
        {"name": "Total Revenue",   "formula": "sum(revenue)",              "description": "Top-line revenue for the period."},
        {"name": "Total Expenses",  "formula": "sum(expense)",              "description": "Total operating expenditure."},
        {"name": "Net Profit",      "formula": "revenue - expenses",        "description": "Bottom-line profitability."},
        {"name": "Margin",          "formula": "net_profit / revenue",      "description": "Net profit as a % of revenue."},
        {"name": "Budget Variance", "formula": "actual - budget",           "description": "Deviation from plan."},
    ],
    "hr": [
        {"name": "Headcount",          "formula": "count(employee_id)",    "description": "Total active employees."},
        {"name": "Attrition Rate",     "formula": "left / total",          "description": "% of workforce that departed in the period."},
        {"name": "Avg Salary",         "formula": "mean(salary)",          "description": "Average compensation across the workforce."},
        {"name": "Department Count",   "formula": "nunique(department)",   "description": "Number of distinct departments."},
        {"name": "Avg Tenure",         "formula": "mean(tenure)",          "description": "Mean years of service."},
        {"name": "Avg Performance",    "formula": "mean(performance)",     "description": "Average performance score across the workforce."},
        {"name": "Remote %",           "formula": "remote / total",        "description": "% of workforce working remotely."},
    ],
    "saas": [
        {"name": "Total MRR",           "formula": "sum(mrr)",                         "description": "Total monthly recurring revenue — the SaaS north star metric."},
        {"name": "Implied ARR",         "formula": "sum(mrr) * 12",                    "description": "Annualised recurring revenue run rate."},
        {"name": "Churn Rate",          "formula": "churned / total",                  "description": "% of accounts that cancelled in the period."},
        {"name": "Avg NPS Score",       "formula": "mean(nps_score)",                  "description": "Net Promoter Score — customer satisfaction and loyalty indicator."},
        {"name": "Avg Seats",           "formula": "mean(seats)",                      "description": "Average number of licensed seats per account."},
        {"name": "Revenue per Seat",    "formula": "mrr / seats",                      "description": "ARPU at the seat level — pricing efficiency signal."},
        {"name": "Active Accounts",     "formula": "count(status=active)",              "description": "Number of currently active subscriptions."},
        {"name": "Avg Contract Length", "formula": "mean(contract_months)",             "description": "Average contract duration in months — retention signal."},
        {"name": "MoM MRR Growth",      "formula": "last_month / prev_month - 1",      "description": "Month-over-month growth in recurring revenue."},
    ],
    "ecommerce": [
        {"name": "Total Revenue",       "formula": "sum(revenue)",                     "description": "Gross revenue across all orders."},
        {"name": "Total Orders",        "formula": "count(order_id)",                  "description": "Total number of orders placed."},
        {"name": "Avg Order Value",     "formula": "revenue / orders",                 "description": "Mean revenue per order — key lever for growth."},
        {"name": "Return Rate",         "formula": "returned_orders / total_orders",   "description": "% of orders returned — impacts net revenue."},
        {"name": "Avg Discount",        "formula": "mean(discount_pct)",               "description": "Average promotional discount applied."},
        {"name": "Avg Days to Ship",    "formula": "mean(days_to_ship)",               "description": "Mean fulfilment time — customer experience signal."},
        {"name": "MoM Revenue Growth",  "formula": "last_month / prev_month - 1",      "description": "Month-over-month revenue trend."},
        {"name": "Revenue by Channel",  "formula": "groupby(channel, revenue)",        "description": "Revenue attribution by acquisition channel."},
        {"name": "Revenue by Category", "formula": "groupby(category, revenue)",       "description": "Revenue breakdown by product category."},
    ],
    "retail": [
        {"name": "Avg Gross Margin",    "formula": "mean(margin_pct)",                 "description": "Average profit margin % across SKUs."},
        {"name": "Stockout Rate",       "formula": "below_reorder / total_skus",       "description": "% of SKUs at or below reorder point — supply risk signal."},
        {"name": "Inventory Value",     "formula": "sum(units_in_stock * sell_price)",  "description": "Total value of current stock at retail price."},
        {"name": "Avg Units in Stock",  "formula": "mean(units_in_stock)",             "description": "Average on-hand quantity per SKU."},
        {"name": "Avg Days Cover",      "formula": "units_in_stock / (sold_30d / 30)", "description": "Days of stock remaining at current sell-through rate."},
        {"name": "Inventory Turnover",  "formula": "units_sold_30d / units_in_stock",  "description": "How quickly inventory is sold relative to stock levels."},
        {"name": "Avg Sell Price",      "formula": "mean(sell_price)",                 "description": "Average retail price across SKUs."},
        {"name": "Est. 30d Revenue",    "formula": "sum(units_sold_30d * sell_price)",  "description": "Estimated 30-day revenue based on recent sell-through."},
    ],
    "general": [
        {"name": "Row Count",     "formula": "len(df)",            "description": "Total records in the dataset."},
        {"name": "Completeness",  "formula": "non_null / total",   "description": "% of cells with non-null values."},
        {"name": "Unique Values", "formula": "nunique per column",  "description": "Cardinality of key columns."},
    ],
}

# ── Column alias map for flexible matching ─────────────────────────────────────
_COLUMN_ALIASES: dict[str, list[str]] = {
    # Core financial
    "revenue":               ["revenue", "sales", "amount", "booking", "income", "gmv"],
    "spend":                 ["spend", "cost", "ad_spend", "media_spend", "budget_used"],
    # Marketing
    "clicks":                ["clicks", "click", "link_clicks"],
    "impressions":           ["impressions", "impression", "views", "reach"],
    "conversions":           ["conversions", "conversion", "leads"],
    # Sales / ecommerce
    "quantity":              ["quantity", "qty", "units", "volume"],
    "discount":              ["discount", "disc", "markdown", "discount_pct", "discount_rate"],
    "days_to_ship":          ["days_to_ship", "shipping_days", "fulfillment_days", "lead_time"],
    "return_flag":           ["return_flag", "returned", "is_return", "is_returned", "refunded"],
    # Operations
    "response_time_hours":   ["response_time", "response_time_hours", "first_response"],
    "resolution_time_hours": ["resolution_time", "resolution_time_hours", "time_to_close"],
    # HR
    "salary":                ["salary", "compensation", "pay", "wage"],
    "tenure":                ["tenure", "years_of_service", "seniority", "tenure_years"],
    "performance":           ["performance", "performance_score", "rating", "perf_score"],
    # SaaS
    "mrr":                   ["mrr", "monthly_recurring_revenue", "monthly_revenue"],
    "nps_score":             ["nps_score", "nps", "net_promoter_score", "net_promoter"],
    "seats":                 ["seats", "licenses", "seat_count", "user_count"],
    "contract_months":       ["contract_months", "contract_length", "term_months"],
    "support_tickets":       ["support_tickets", "tickets", "support_cases"],
    # Retail / inventory
    "margin_pct":            ["margin_pct", "gross_margin", "margin_percent", "profit_margin"],
    "units_in_stock":        ["units_in_stock", "stock_qty", "on_hand", "inventory_qty", "stock"],
    "reorder_point":         ["reorder_point", "reorder_level", "min_stock", "safety_stock"],
    "units_sold_30d":        ["units_sold_30d", "units_sold", "monthly_sold", "qty_sold"],
    "cost_price":            ["cost_price", "unit_cost", "purchase_price", "cogs"],
    "sell_price":            ["sell_price", "selling_price", "unit_price", "retail_price", "price"],
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
    domain_kpis  = _KPI_CATALOGUE.get(domain, [])
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
        "marketing":  _calc_marketing,
        "sales":      _calc_sales,
        "operations": _calc_operations,
        "finance":    _calc_finance,
        "hr":         _calc_hr,
        "saas":       _calc_saas,
        "ecommerce":  _calc_ecommerce,
        "retail":     _calc_retail,
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
        out["Total Revenue"]   = _fmt_currency(total_rev)
        out["Avg Order Value"] = _fmt_currency(total_rev / len(df)) if len(df) else "$0"
        growth = _calc_mom_growth(df, r["revenue"])
        if growth is not None:
            out["MoM Revenue Growth"] = f"{growth:+.1f}%"
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
    if r.get("performance"):
        out["Avg Performance"] = f"{df[r['performance']].mean():.1f}"
    status_col = _find_col(df, ["status", "employment_status"])
    if status_col:
        active = df[status_col].str.lower().isin(["active", "employed"]).sum()
        left   = df[status_col].str.lower().isin(["left", "terminated", "resigned", "inactive"]).sum()
        if active + left > 0:
            out["Attrition Rate"] = f"{left / (active + left) * 100:.1f}%"
    remote_col = _find_col(df, ["remote", "remote_status", "work_mode"])
    if remote_col:
        remote_count = df[remote_col].str.lower().isin(["remote", "yes", "fully remote"]).sum()
        if len(df):
            out["Remote %"] = f"{remote_count / len(df) * 100:.1f}%"
    return out


def _calc_saas(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    if r.get("mrr"):
        mrr_total = df[r["mrr"]].sum()
        out["Total MRR"]    = _fmt_currency(mrr_total)
        out["Implied ARR"]  = _fmt_currency(mrr_total * 12)
        growth = _calc_mom_growth(df, r["mrr"])
        if growth is not None:
            out["MoM MRR Growth"] = f"{growth:+.1f}%"
    if r.get("nps_score"):
        out["Avg NPS Score"] = f"{df[r['nps_score']].mean():.1f}"
    if r.get("seats"):
        out["Avg Seats"] = f"{df[r['seats']].mean():.1f}"
        if r.get("mrr"):
            avg_seats = df[r["seats"]].mean()
            avg_mrr   = df[r["mrr"]].mean()
            if avg_seats > 0:
                out["Revenue per Seat"] = _fmt_currency(avg_mrr / avg_seats)
    if r.get("contract_months"):
        out["Avg Contract Length"] = f"{df[r['contract_months']].mean():.1f} mo"
    if r.get("support_tickets"):
        out["Avg Support Tickets"] = f"{df[r['support_tickets']].mean():.1f}"
    status_col = _find_col(df, ["status", "subscription_status"])
    if status_col:
        active_count  = df[status_col].str.lower().isin(["active", "paying"]).sum()
        churned_count = df[status_col].str.lower().isin(["churned", "cancelled", "canceled"]).sum()
        total = active_count + churned_count
        if total > 0:
            out["Active Accounts"] = f"{int(active_count):,}"
            out["Churn Rate"]      = f"{churned_count / total * 100:.1f}%"
    return out


def _calc_ecommerce(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    if r.get("revenue"):
        total_rev = df[r["revenue"]].sum()
        out["Total Revenue"]   = _fmt_currency(total_rev)
        out["Total Orders"]    = f"{len(df):,}"
        out["Avg Order Value"] = _fmt_currency(total_rev / len(df)) if len(df) else "$0"
        growth = _calc_mom_growth(df, r["revenue"])
        if growth is not None:
            out["MoM Revenue Growth"] = f"{growth:+.1f}%"
    if r.get("return_flag"):
        rc = df[r["return_flag"]]
        # Handle boolean or 0/1 integer columns
        if pd.api.types.is_bool_dtype(rc):
            returns = rc.sum()
        else:
            returns = (rc == 1).sum() + rc.astype(str).str.lower().isin(["true", "yes", "1"]).sum()
        if len(df):
            out["Return Rate"] = f"{returns / len(df) * 100:.1f}%"
    if r.get("discount"):
        out["Avg Discount"] = f"{df[r['discount']].mean() * 100:.1f}%"
    if r.get("days_to_ship"):
        out["Avg Days to Ship"] = f"{df[r['days_to_ship']].mean():.1f} days"
    return out


def _calc_retail(df: pd.DataFrame, r: dict) -> dict:
    out = {}
    if r.get("margin_pct"):
        out["Avg Gross Margin"] = f"{df[r['margin_pct']].mean():.1f}%"
    if r.get("units_in_stock") and r.get("sell_price"):
        inv_value = (df[r["units_in_stock"]] * df[r["sell_price"]]).sum()
        out["Inventory Value"] = _fmt_currency(inv_value)
    if r.get("units_in_stock"):
        out["Avg Units in Stock"] = f"{df[r['units_in_stock']].mean():.0f}"
    if r.get("units_in_stock") and r.get("reorder_point"):
        stockout_count = (df[r["units_in_stock"]] <= df[r["reorder_point"]]).sum()
        out["Stockout Rate"] = f"{stockout_count / len(df) * 100:.1f}%"
    if r.get("units_in_stock") and r.get("units_sold_30d"):
        stock  = df[r["units_in_stock"]].replace(0, pd.NA)
        sold   = df[r["units_sold_30d"]]
        daily_rate = sold / 30
        days_cover = (stock / daily_rate.replace(0, pd.NA)).dropna()
        if not days_cover.empty:
            out["Avg Days Cover"] = f"{days_cover.mean():.0f} days"
        turnover = (sold / stock.fillna(1)).mean()
        out["Inventory Turnover"] = f"{turnover:.2f}x"
    if r.get("units_sold_30d") and r.get("sell_price"):
        est_rev = (df[r["units_sold_30d"]] * df[r["sell_price"]]).sum()
        out["Est. 30d Revenue"] = _fmt_currency(est_rev)
    return out


# ── Growth rate helper ────────────────────────────────────────────────────────

def _calc_mom_growth(df: pd.DataFrame, value_col: str) -> float | None:
    """
    Compute month-over-month growth % for value_col using the first detected date column.
    Returns None if insufficient data or no date column found.
    """
    date_col = _find_date_col(df)
    if not date_col:
        return None

    try:
        tmp = df[[date_col, value_col]].copy()
        tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")
        tmp = tmp.dropna(subset=[date_col])
        if tmp.empty:
            return None

        tmp["_month"] = tmp[date_col].dt.to_period("M")
        monthly = tmp.groupby("_month")[value_col].sum().sort_index()

        if len(monthly) < 2:
            return None

        prev = monthly.iloc[-2]
        last = monthly.iloc[-1]
        if prev == 0:
            return None

        return (last - prev) / abs(prev) * 100
    except Exception:
        return None


def _find_date_col(df: pd.DataFrame) -> str | None:
    """Return the first date-like column found in df."""
    for col in df.select_dtypes(include=["datetime", "datetimetz"]).columns:
        return col
    for col in df.select_dtypes(include="object").columns:
        if any(kw in col.lower() for kw in ["date", "month", "time", "dt", "created", "updated"]):
            return col
    return None


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
    """Return the first column name matching any fragment, preferring exact matches."""
    exact = {col.lower(): col for col in df.columns}
    for frag in fragments:
        if frag in exact:
            return exact[frag]
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
