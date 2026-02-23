# scripts/04_export_excel_ready.py
from __future__ import annotations

from pathlib import Path
import pandas as pd

PROCESSED_DIR = Path("data/processed")
EXCEL_DIR = Path("deliverables/excel_inputs")

def main():
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)

    # Inputs
    kpi_daily = pd.read_csv(PROCESSED_DIR / "kpi_daily.csv")
    kpi_event = pd.read_csv(PROCESSED_DIR / "kpi_event.csv")
    dim_events = pd.read_csv(PROCESSED_DIR / "dim_events.csv")

    # ---- Clean dates (robuste) ----
    for df, col in [(kpi_daily, "date"), (kpi_event, "event_date"), (dim_events, "event_date")]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    # ---- Force numeric columns where possible ----
    def to_num(df: pd.DataFrame):
        for c in df.columns:
            if c.lower() in {"date", "event_date", "event_name", "venue_name", "genre", "quartier"}:
                continue
            # try convert
            df[c] = pd.to_numeric(df[c], errors="ignore")
        return df

    kpi_daily = to_num(kpi_daily)
    kpi_event = to_num(kpi_event)

    # Save
    kpi_daily.to_csv(EXCEL_DIR / "kpi_daily_excel.csv", index=False, encoding="utf-8")
    kpi_event.to_csv(EXCEL_DIR / "kpi_event_excel.csv", index=False, encoding="utf-8")
    dim_events.to_csv(EXCEL_DIR / "dim_events_excel.csv", index=False, encoding="utf-8")

    print("✅ Excel-ready exports:")
    for p in [
        EXCEL_DIR / "kpi_daily_excel.csv",
        EXCEL_DIR / "kpi_event_excel.csv",
        EXCEL_DIR / "dim_events_excel.csv",
    ]:
        print("-", p.as_posix())

if __name__ == "__main__":
    main()
