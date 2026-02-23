# scripts/03_prepare_exports.py
from __future__ import annotations

from pathlib import Path
import pandas as pd


RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


# --- petits helpers ---
def _rename_if_present(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    present = {k: v for k, v in mapping.items() if k in df.columns}
    return df.rename(columns=present)


def _ensure_column(df: pd.DataFrame, col: str, default=None) -> pd.DataFrame:
    if col not in df.columns:
        df[col] = default
    return df


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # --- Read raw ---
    events = pd.read_csv(RAW_DIR / "events.csv")
    tx = pd.read_csv(RAW_DIR / "transactions.csv")
    att = pd.read_csv(RAW_DIR / "attendance.csv")

    # --- Normalize column names (aliases) ---
    # Events
    events = _rename_if_present(events, {
        "date_time": "event_datetime",
        "event_date": "event_datetime",
        "date": "event_datetime",
    })

    # Transactions
    tx = _rename_if_present(tx, {
        "transaction_id": "tx_id",
        "purchase_datetime": "purchase_datetime",
        "purchase_date": "purchase_datetime",
        "purchase_time": "purchase_datetime",
        "lead_time_days": "days_before_event",
    })

    # Attendance
    att = _rename_if_present(att, {
        "transaction_id": "tx_id",
        "attended": "attended",  # si déjà ok
    })

    # --- Required columns safety ---
    events = _ensure_column(events, "event_id")
    events = _ensure_column(events, "event_datetime")
    events = _ensure_column(events, "capacity", 0)

    tx = _ensure_column(tx, "tx_id")
    tx = _ensure_column(tx, "event_id")
    tx = _ensure_column(tx, "purchase_datetime")
    tx = _ensure_column(tx, "tickets_qty", 1)
    tx = _ensure_column(tx, "price_paid_total", None)
    tx = _ensure_column(tx, "days_before_event", None)

    att = _ensure_column(att, "tx_id")
    att = _ensure_column(att, "attended", None)
    att = _ensure_column(att, "no_show", None)

    # --- Parse datetimes ---
    events["event_datetime"] = pd.to_datetime(events["event_datetime"], errors="coerce")
    tx["purchase_datetime"] = pd.to_datetime(tx["purchase_datetime"], errors="coerce")

    # --- Build attendance clean ---
    # Si on a attended (0/1), on calcule no_show
    if att["no_show"].isna().all() and att["attended"].notna().any():
        att["no_show"] = 1 - att["attended"].astype(int)

    # --- Enrich transactions with event info ---
    # On merge pour récupérer event_datetime, capacity, etc.
    dim_events = events.copy()

    bi = tx.merge(
        dim_events,
        on="event_id",
        how="left",
        suffixes=("", "_ev")
    )

    bi = bi.merge(
        att[["tx_id", "attended", "no_show"]],
        on="tx_id",
        how="left"
    )

    # --- Derived columns ---
    # event_day (date)
    bi["event_day"] = pd.to_datetime(bi["event_datetime"], errors="coerce").dt.date

    # lead time
    # si days_before_event est absent/NaN, on le calcule
    if "days_before_event" not in bi.columns:
        bi["days_before_event"] = None

    mask_missing_lead = bi["days_before_event"].isna() & bi["purchase_datetime"].notna() & bi["event_datetime"].notna()
    bi.loc[mask_missing_lead, "days_before_event"] = (
        (bi.loc[mask_missing_lead, "event_datetime"] - bi.loc[mask_missing_lead, "purchase_datetime"])
        .dt.days
    )

    bi["days_before_event"] = pd.to_numeric(bi["days_before_event"], errors="coerce")

    # purchase_day (date)
    bi["purchase_day"] = bi["purchase_datetime"].dt.date

    # avg ticket price
    if bi["price_paid_total"].notna().any():
        bi["avg_ticket_price"] = pd.to_numeric(bi["price_paid_total"], errors="coerce") / pd.to_numeric(bi["tickets_qty"], errors="coerce")
    else:
        bi["avg_ticket_price"] = None

    # Early / Late flags
    bi["is_early"] = (bi["days_before_event"] > 45).fillna(False).astype(int)
    bi["is_late"] = (bi["days_before_event"] <= 7).fillna(False).astype(int)

    # --- Fact tables (Power BI-friendly) ---
    dim_events_out = dim_events.copy()
    fact_transactions_out = bi.copy()

    fact_attendance_out = att[["tx_id", "attended", "no_show"]].copy()

    # KPI per event (hyper utile pour une page “direction”)
    kpi_event = (
        bi.groupby("event_id", as_index=False)
        .agg(
            tickets_sold=("tickets_qty", "sum"),
            revenue=("price_paid_total", "sum"),
            avg_basket=("price_paid_total", "mean"),
            first_purchase=("purchase_datetime", "min"),
            last_purchase=("purchase_datetime", "max"),
            no_show_rate=("no_show", "mean"),
        )
    )
    kpi_event = kpi_event.merge(dim_events[["event_id", "event_name", "venue_name", "event_datetime", "capacity"]]
                                if "event_name" in dim_events.columns else dim_events[["event_id", "event_datetime", "capacity"]],
                                on="event_id", how="left")

    kpi_event["fill_rate"] = (kpi_event["tickets_sold"] / pd.to_numeric(kpi_event["capacity"], errors="coerce")).replace([pd.NA, float("inf")], pd.NA)

    cap = pd.to_numeric(kpi_event["capacity"], errors="coerce").replace(0, pd.NA)
    kpi_event["fill_rate"] = (kpi_event["tickets_sold"] / cap).clip(lower=0, upper=1)

    # KPI daily (ventes/jour)
    kpi_daily = (
        bi.groupby("purchase_day", as_index=False)
        .agg(
            tickets_sold=("tickets_qty", "sum"),
            revenue=("price_paid_total", "sum"),
            avg_basket=("price_paid_total", "mean"),
            avg_lead_time=("days_before_event", "mean"),
            tx_count=("tx_id", "nunique"),
        )
        .sort_values("purchase_day")
    )

    # --- Write outputs (NOT versioned) ---
    # UTF-8-SIG = Excel friendly
    dim_events_out.to_csv(PROCESSED_DIR / "dim_events.csv", index=False, encoding="utf-8-sig")
    fact_transactions_out.to_csv(PROCESSED_DIR / "fact_transactions.csv", index=False, encoding="utf-8-sig")
    fact_attendance_out.to_csv(PROCESSED_DIR / "fact_attendance.csv", index=False, encoding="utf-8-sig")
    kpi_event.to_csv(PROCESSED_DIR / "kpi_event.csv", index=False, encoding="utf-8-sig")
    kpi_daily.to_csv(PROCESSED_DIR / "kpi_daily.csv", index=False, encoding="utf-8-sig")

    # Optionnel : un flat “tout-en-un” si tu veux vite tester
    fact_transactions_out.to_csv(PROCESSED_DIR / "billetterie_bi.csv", index=False, encoding="utf-8-sig")

    print("✅ Exports Power BI terminés :")
    for f in ["dim_events.csv", "fact_transactions.csv", "fact_attendance.csv", "kpi_event.csv", "kpi_daily.csv", "billetterie_bi.csv"]:
        p = (PROCESSED_DIR / f)
        print(f"- {p.as_posix()} ({p.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
