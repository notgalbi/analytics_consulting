"""
Generate 4 realistic CSV files with business storytelling, seasonality, and patterns.
Uses only stdlib + pandas + numpy.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import random

OUTPUT_DIR = Path("/Users/notricco/_Projects/data_dashboard_mvp/sample_data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(42)
random.seed(42)

# ─────────────────────────────────────────────────────────────
# 1. REAL ESTATE LISTINGS
# ─────────────────────────────────────────────────────────────
def generate_real_estate(n=300):
    print("Generating real_estate_listings.csv ...")

    # Date range with spring/summer peak
    all_dates = pd.date_range("2023-01-01", "2024-06-30", freq="D")
    month_weights = {
        1: 0.5, 2: 0.6, 3: 1.4, 4: 1.6, 5: 1.8, 6: 1.7,
        7: 1.5, 8: 1.2, 9: 1.0, 10: 0.9, 11: 0.7, 12: 0.6,
    }
    date_weights = np.array([month_weights[d.month] for d in all_dates], dtype=float)
    date_weights /= date_weights.sum()
    list_dates = pd.to_datetime(
        RNG.choice(all_dates, size=n, replace=True, p=date_weights)
    )

    # Property type
    prop_types = RNG.choice(
        ["House", "Condo", "Townhouse", "Land"],
        size=n,
        p=[0.50, 0.30, 0.15, 0.05],
    )

    # Neighborhoods with price_per_sqft ranges
    neighborhoods = ["Downtown", "Riverside", "Oakwood", "Hillcrest", "Bayside", "Northgate"]
    nbhd_ppsf = {
        "Downtown": 350,
        "Riverside": 280,
        "Oakwood": 210,
        "Hillcrest": 390,
        "Bayside": 420,
        "Northgate": 165,
    }
    nbhd_speed = {  # lower = faster market
        "Downtown": 1.0,
        "Riverside": 1.1,
        "Oakwood": 1.2,
        "Hillcrest": 0.7,
        "Bayside": 0.6,
        "Northgate": 1.4,
    }
    neighborhood = RNG.choice(neighborhoods, size=n)

    # Bedrooms: correlated with property type
    bedrooms = np.zeros(n, dtype=int)
    for i, pt in enumerate(prop_types):
        if pt == "Land":
            bedrooms[i] = 0
        elif pt == "Condo":
            bedrooms[i] = RNG.choice([1, 2, 3], p=[0.35, 0.45, 0.20])
        elif pt == "Townhouse":
            bedrooms[i] = RNG.choice([2, 3, 4], p=[0.25, 0.55, 0.20])
        else:  # House
            bedrooms[i] = RNG.choice([2, 3, 4, 5], p=[0.10, 0.40, 0.35, 0.15])

    # Bathrooms (0.5 steps)
    bathrooms = np.zeros(n)
    for i, beds in enumerate(bedrooms):
        if beds == 0:
            bathrooms[i] = 0
        else:
            raw = RNG.normal(beds * 0.7, 0.5)
            raw = max(1.0, min(4.0, raw))
            bathrooms[i] = round(raw * 2) / 2  # round to nearest 0.5

    # Sqft: correlated with bedrooms
    sqft = np.zeros(n, dtype=int)
    for i, beds in enumerate(bedrooms):
        if beds == 0:
            sqft[i] = int(RNG.integers(5000, 50000))  # raw land (sqft)
        else:
            base = 400 + beds * 350
            sq = RNG.normal(base, base * 0.15)
            sqft[i] = int(max(500, min(5000, sq)))

    # Price per sqft: neighborhood base + property type modifier
    pt_modifier = {"House": 1.0, "Condo": 1.10, "Townhouse": 1.05, "Land": 0.05}
    asking_price = np.zeros(n)
    for i in range(n):
        ppsf_base = nbhd_ppsf[neighborhood[i]]
        ppsf = ppsf_base * pt_modifier[prop_types[i]] * RNG.uniform(0.92, 1.08)
        if prop_types[i] == "Land":
            asking_price[i] = round(ppsf * sqft[i] / 1000) * 1000
        else:
            asking_price[i] = round(ppsf * sqft[i] / 1000) * 1000

    # Days on market
    dom_base = {"House": 45, "Condo": 28, "Townhouse": 38, "Land": 90}
    days_on_market = np.zeros(n, dtype=int)
    for i in range(n):
        base_dom = dom_base[prop_types[i]] * nbhd_speed[neighborhood[i]]
        dom = int(RNG.lognormal(np.log(max(base_dom, 7)), 0.5))
        days_on_market[i] = max(7, min(180, dom))

    # Sold status (85%)
    sold = RNG.random(n) < 0.85

    # Sale price: asking * negotiation factor
    sale_price = np.full(n, np.nan)
    sale_date = np.full(n, "", dtype=object)
    for i in range(n):
        if sold[i]:
            if prop_types[i] == "Land" or days_on_market[i] > 100:
                factor = RNG.uniform(0.93, 0.97)
            else:
                factor = RNG.uniform(0.97, 1.02)
            sale_price[i] = round(asking_price[i] * factor / 1000) * 1000
            sale_date[i] = (list_dates[i] + pd.Timedelta(days=int(days_on_market[i]))).strftime("%Y-%m-%d")

    # Agents
    agents = [
        "Sarah M.", "James T.", "Linda K.", "Robert P.",
        "Karen B.", "Michael H.", "Angela W.", "David C.",
    ]
    agent = RNG.choice(agents, size=n)

    df = pd.DataFrame({
        "list_date": list_dates.strftime("%Y-%m-%d"),
        "sale_date": sale_date,
        "property_type": prop_types,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "sqft": sqft,
        "neighborhood": neighborhood,
        "asking_price": asking_price.astype(int),
        "sale_price": pd.array(
            [int(x) if not np.isnan(x) else None for x in sale_price],
            dtype=pd.Int64Dtype(),
        ),
        "days_on_market": days_on_market,
        "sold": sold,
        "agent": agent,
    })

    out = OUTPUT_DIR / "real_estate_listings.csv"
    df.to_csv(out, index=False)
    print(f"  Saved {len(df)} rows to {out}")
    return df


# ─────────────────────────────────────────────────────────────
# 2. RESTAURANT DAILY
# ─────────────────────────────────────────────────────────────
def generate_restaurant(n_months=18):
    print("Generating restaurant_daily.csv ...")

    dates = pd.date_range("2023-07-01", "2024-12-31", freq="D")

    rows = []
    for dt in dates:
        dow = dt.day_name()  # Monday, Tuesday, ...
        dow_short = dt.strftime("%a")  # Mon, Tue, ...
        is_weekend = dow in ("Saturday", "Sunday")
        month = dt.month

        # Seasonal multiplier
        seasonal = {
            1: 0.72, 2: 0.75, 3: 0.88, 4: 0.93, 5: 0.97,
            6: 1.02, 7: 1.05, 8: 1.03, 9: 0.98, 10: 0.95,
            11: 1.00, 12: 1.15,
        }[month]

        # Covers
        base_covers = 90 if is_weekend else 65
        covers_raw = base_covers * seasonal * RNG.uniform(0.80, 1.20)
        covers = int(max(20, min(180, covers_raw)))

        # Avg check
        base_check = 38 if is_weekend else 28
        if month == 12:
            base_check *= 1.12
        avg_check = round(base_check * RNG.uniform(0.90, 1.10), 2)
        avg_check = max(18, min(55, avg_check))

        # Revenue
        revenue = round(covers * avg_check * RNG.uniform(0.98, 1.02), 2)

        # Costs
        food_cost_pct = round(RNG.uniform(28, 38), 1)
        labor_cost_pct = round(
            max(25, min(40, 32 + (80 - covers) * 0.08 + RNG.uniform(-2, 2))), 1
        )

        gross_profit = round(revenue * (1 - food_cost_pct / 100 - labor_cost_pct / 100), 2)

        # Reservations
        res_pct = RNG.uniform(0.55, 0.75) if is_weekend else RNG.uniform(0.40, 0.60)
        reservations = int(covers * res_pct)
        walk_ins = covers - reservations

        # No-shows
        no_show_pct = RNG.uniform(0.03, 0.15)
        no_shows = int(reservations * no_show_pct)

        rows.append({
            "date": dt.strftime("%Y-%m-%d"),
            "day_of_week": dow_short,
            "covers": covers,
            "avg_check": avg_check,
            "revenue": revenue,
            "food_cost_pct": food_cost_pct,
            "labor_cost_pct": labor_cost_pct,
            "gross_profit": gross_profit,
            "reservations": reservations,
            "walk_ins": walk_ins,
            "no_shows": no_shows,
        })

    df = pd.DataFrame(rows)
    out = OUTPUT_DIR / "restaurant_daily.csv"
    df.to_csv(out, index=False)
    print(f"  Saved {len(df)} rows to {out}")
    return df


# ─────────────────────────────────────────────────────────────
# 3. GYM MEMBERSHIP
# ─────────────────────────────────────────────────────────────
def generate_gym(n=450):
    print("Generating gym_membership.csv ...")

    all_dates = pd.date_range("2022-01-01", "2024-06-30", freq="D")

    # January spike each year, smaller September spike
    def join_weight(d):
        if d.month == 1:
            return 3.5
        if d.month == 9:
            return 1.8
        if d.month == 2:
            return 1.5
        if d.month in (5, 6):
            return 1.2
        return 1.0

    dw = np.array([join_weight(d) for d in all_dates], dtype=float)
    dw /= dw.sum()
    join_dates = pd.to_datetime(RNG.choice(all_dates, size=n, replace=True, p=dw))

    plan_types = RNG.choice(["Monthly", "Annual", "Premium"], size=n, p=[0.40, 0.35, 0.25])

    # Status: churn by plan
    status_arr = []
    for pt in plan_types:
        if pt == "Monthly":
            s = RNG.choice(["Active", "Cancelled", "Frozen"], p=[0.70, 0.25, 0.05])
        elif pt == "Annual":
            s = RNG.choice(["Active", "Cancelled", "Frozen"], p=[0.87, 0.08, 0.05])
        else:  # Premium
            s = RNG.choice(["Active", "Cancelled", "Frozen"], p=[0.90, 0.05, 0.05])
        status_arr.append(s)

    # MRR
    mrr_base = {"Monthly": 49, "Annual": 35, "Premium": 89}
    mrr = np.array([
        round(mrr_base[pt] * RNG.uniform(0.97, 1.03), 2) for pt in plan_types
    ])

    # NPS: Premium scores higher
    nps_mean = {"Monthly": 6.5, "Annual": 7.0, "Premium": 8.2}
    nps_score = np.array([
        int(max(1, min(10, round(RNG.normal(nps_mean[pt], 1.2))))) for pt in plan_types
    ])

    contract_months = {"Monthly": 1, "Annual": 12, "Premium": 24}
    contracts = np.array([contract_months[pt] for pt in plan_types])

    age_groups = RNG.choice(["18-25", "26-35", "36-45", "46-55", "55+"], size=n,
                             p=[0.20, 0.30, 0.25, 0.15, 0.10])

    goals = RNG.choice(
        ["Weight Loss", "Muscle Building", "General Fitness", "Sports Training", "Rehabilitation"],
        size=n,
        p=[0.30, 0.25, 0.25, 0.12, 0.08],
    )

    industries = [
        "Technology", "Healthcare", "Finance", "Education", "Retail",
        "Construction", "Hospitality", "Legal", "Manufacturing", "Real Estate",
    ]
    industry = RNG.choice(industries, size=n)

    # Visits per month
    visits = np.zeros(n, dtype=int)
    for i, s in enumerate(status_arr):
        if s == "Active":
            visits[i] = int(max(1, min(25, RNG.normal(12, 4))))
        elif s == "Frozen":
            visits[i] = int(RNG.choice([0, 1, 2], p=[0.60, 0.25, 0.15]))
        else:  # Cancelled
            visits[i] = 0

    df = pd.DataFrame({
        "join_date": join_dates.strftime("%Y-%m-%d"),
        "plan_type": plan_types,
        "status": status_arr,
        "mrr": mrr,
        "nps_score": nps_score,
        "contract_months": contracts,
        "age_group": age_groups,
        "primary_goal": goals,
        "visits_per_month": visits,
        "industry": industry,
    })

    out = OUTPUT_DIR / "gym_membership.csv"
    df.to_csv(out, index=False)
    print(f"  Saved {len(df)} rows to {out}")
    return df


# ─────────────────────────────────────────────────────────────
# 4. CLINIC APPOINTMENTS
# ─────────────────────────────────────────────────────────────
def generate_clinic(n=600):
    print("Generating clinic_appointments.csv ...")

    # Weekdays only
    all_dates = pd.bdate_range("2023-01-01", "2024-12-31")
    appt_dates = pd.to_datetime(RNG.choice(all_dates, size=n, replace=True))

    appt_types = RNG.choice(
        ["Consultation", "Follow-up", "Procedure"],
        size=n,
        p=[0.40, 0.35, 0.25],
    )

    departments = RNG.choice(
        ["General Practice", "Cardiology", "Orthopedics", "Dermatology", "Mental Health"],
        size=n,
        p=[0.35, 0.20, 0.20, 0.15, 0.10],
    )

    # Wait time: General Practice longest
    dept_wait = {
        "General Practice": 28,
        "Cardiology": 20,
        "Orthopedics": 18,
        "Dermatology": 15,
        "Mental Health": 12,
    }
    wait_time = np.array([
        int(max(5, min(45, RNG.normal(dept_wait[d], 8)))) for d in departments
    ])

    # Duration: Procedures longest, Follow-ups shortest
    type_duration = {"Consultation": 35, "Follow-up": 20, "Procedure": 60}
    duration = np.array([
        int(max(15, min(90, RNG.normal(type_duration[t], 12)))) for t in appt_types
    ])

    # No-show: 12% rate
    no_show = RNG.random(n) < 0.12

    # Status derived from no_show + some cancellations
    cancelled = (~no_show) & (RNG.random(n) < 0.06)
    status = np.where(no_show, "No-Show", np.where(cancelled, "Cancelled", "Completed"))

    # Billing
    type_bill = {"Consultation": 180, "Follow-up": 110, "Procedure": 520}
    dept_bill_mod = {
        "General Practice": 0.85,
        "Cardiology": 1.30,
        "Orthopedics": 1.25,
        "Dermatology": 1.05,
        "Mental Health": 0.90,
    }
    billing = np.array([
        round(
            type_bill[appt_types[i]] * dept_bill_mod[departments[i]] * RNG.uniform(0.85, 1.15),
            2,
        )
        for i in range(n)
    ])
    billing = np.clip(billing, 75, 800)

    insurance = RNG.choice(
        ["Private", "Medicare", "Medicaid", "Self-pay"],
        size=n,
        p=[0.55, 0.25, 0.15, 0.05],
    )

    # Patient satisfaction: inverse with wait time, varies by dept
    dept_sat_base = {
        "General Practice": 3.5,
        "Cardiology": 4.0,
        "Orthopedics": 4.1,
        "Dermatology": 4.2,
        "Mental Health": 4.3,
    }
    satisfaction = np.array([
        round(
            max(
                1.0,
                min(
                    5.0,
                    dept_sat_base[departments[i]]
                    - (wait_time[i] - 15) * 0.02
                    + RNG.normal(0, 0.4),
                ),
            ),
            1,
        )
        for i in range(n)
    ])
    # No-shows/cancellations don't generate a satisfaction score
    satisfaction = np.where(status == "Completed", satisfaction, np.nan)

    df = pd.DataFrame({
        "appointment_date": appt_dates.strftime("%Y-%m-%d"),
        "appointment_type": appt_types,
        "department": departments,
        "wait_time_mins": wait_time,
        "duration_mins": duration,
        "no_show": no_show,
        "billing_amount": billing,
        "insurance_type": insurance,
        "patient_satisfaction": satisfaction,
        "status": status,
    })

    out = OUTPUT_DIR / "clinic_appointments.csv"
    df.to_csv(out, index=False)
    print(f"  Saved {len(df)} rows to {out}")
    return df


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    re_df = generate_real_estate()
    rest_df = generate_restaurant()
    gym_df = generate_gym()
    clinic_df = generate_clinic()

    datasets = {
        "real_estate_listings.csv": re_df,
        "restaurant_daily.csv": rest_df,
        "gym_membership.csv": gym_df,
        "clinic_appointments.csv": clinic_df,
    }

    print("\n" + "=" * 60)
    print("VERIFICATION REPORT")
    print("=" * 60)

    for name, df in datasets.items():
        print(f"\n--- {name} ---")
        print(f"Row count : {len(df)}")
        print(f"Columns   : {list(df.columns)}")
        print("First 2 rows:")
        print(df.head(2).to_string(index=False))
