# scripts/02_quality_checks.py
from __future__ import annotations

from pathlib import Path
import pandas as pd


RAW_DIR = Path("data/raw")
PROC_DIR = Path("data/processed")
DOCS_DIR = Path("docs")

EVENTS_FP = RAW_DIR / "events.csv"
TX_FP = RAW_DIR / "transactions_sample.csv"
ATT_FP = RAW_DIR / "attendance_sample.csv"

REPORT_FP = DOCS_DIR / "data_quality_report.md"
SUMMARY_FP = DOCS_DIR / "quality_summary.csv"



def ensure_dirs() -> None:
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)


def pct(n: int, d: int) -> str:
    if d == 0:
        return "—"
    return f"{(100*n/d):.1f}%"


def main() -> None:
    ensure_dirs()

    # --- Load ---
    missing = [str(p) for p in [EVENTS_FP, TX_FP, ATT_FP] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Fichier(s) manquant(s) dans data/raw :\n- " + "\n- ".join(missing) +
            "\nAstuce: lance d'abord scripts/01_generate_data.py"
        )

    events = pd.read_csv(EVENTS_FP)
    tx = pd.read_csv(TX_FP)
    att = pd.read_csv(ATT_FP)

    # --- Basic schema checks ---
    required_events = {"event_id", "event_name", "venue_name", "date_time", "capacity", "base_price"}
    required_tx = {"transaction_id", "event_id", "purchase_datetime", "tickets_qty", "price_paid_total", "channel", "tariff", "buyer_geo", "lead_time_days"}
    required_att = {"transaction_id", "attended"}

    schema_ok_events = required_events.issubset(set(events.columns))
    schema_ok_tx = required_tx.issubset(set(tx.columns))
    schema_ok_att = required_att.issubset(set(att.columns))

    # --- Types / parsing ---
    # Dates
    events["date_time_parsed"] = pd.to_datetime(events["date_time"], errors="coerce")
    tx["purchase_dt_parsed"] = pd.to_datetime(tx["purchase_datetime"], errors="coerce")

    # Numerics
    for col in ["capacity", "base_price"]:
        events[col] = pd.to_numeric(events[col], errors="coerce")
    for col in ["tickets_qty", "price_paid_total", "lead_time_days"]:
        tx[col] = pd.to_numeric(tx[col], errors="coerce")
    att["attended"] = pd.to_numeric(att["attended"], errors="coerce")

    # --- Missing values ---
    miss_events = events.isna().sum()
    miss_tx = tx.isna().sum()
    miss_att = att.isna().sum()

    # --- Duplicates ---
    dup_event_id = int(events["event_id"].duplicated().sum()) if "event_id" in events.columns else None
    dup_tx_id = int(tx["transaction_id"].duplicated().sum()) if "transaction_id" in tx.columns else None
    dup_att_tx = int(att["transaction_id"].duplicated().sum()) if "transaction_id" in att.columns else None

    # --- Referential integrity ---
    # tx.event_id must exist in events
    orphan_tx = tx[~tx["event_id"].isin(events["event_id"])] if ("event_id" in tx.columns and "event_id" in events.columns) else pd.DataFrame()
    orphan_tx_n = int(len(orphan_tx))

    # attendance.transaction_id must exist in tx
    orphan_att = att[~att["transaction_id"].isin(tx["transaction_id"])] if ("transaction_id" in att.columns and "transaction_id" in tx.columns) else pd.DataFrame()
    orphan_att_n = int(len(orphan_att))

    # --- Business rules ---
    # Non-negative and reasonable
    bad_capacity = int((events["capacity"] <= 0).sum())
    bad_base_price = int((events["base_price"] <= 0).sum())

    bad_qty = int((tx["tickets_qty"] <= 0).sum())
    bad_total = int((tx["price_paid_total"] <= 0).sum())
    bad_lead = int((tx["lead_time_days"] < 0).sum())

    # purchase before event (tolerate missing parse)
    merged = tx.merge(events[["event_id", "date_time_parsed"]], on="event_id", how="left")
    bad_time = merged[
        merged["purchase_dt_parsed"].notna()
        & merged["date_time_parsed"].notna()
        & (merged["purchase_dt_parsed"] > merged["date_time_parsed"])
    ]
    bad_time_n = int(len(bad_time))

    # Attendance values should be 0/1
    bad_att_values = int((~att["attended"].isin([0, 1])).sum())

    # --- Summary table ---
    summary_rows = [
        ("schema", "events required columns present", int(schema_ok_events), 1),
        ("schema", "transactions required columns present", int(schema_ok_tx), 1),
        ("schema", "attendance required columns present", int(schema_ok_att), 1),

        ("duplicates", "events.event_id duplicates", dup_event_id or 0, len(events)),
        ("duplicates", "transactions.transaction_id duplicates", dup_tx_id or 0, len(tx)),
        ("duplicates", "attendance.transaction_id duplicates", dup_att_tx or 0, len(att)),

        ("integrity", "orphan transactions (event_id not in events)", orphan_tx_n, len(tx)),
        ("integrity", "orphan attendance (transaction_id not in transactions)", orphan_att_n, len(att)),

        ("rules", "capacity <= 0", bad_capacity, len(events)),
        ("rules", "base_price <= 0", bad_base_price, len(events)),
        ("rules", "tickets_qty <= 0", bad_qty, len(tx)),
        ("rules", "price_paid_total <= 0", bad_total, len(tx)),
        ("rules", "lead_time_days < 0", bad_lead, len(tx)),
        ("rules", "purchase after event date", bad_time_n, len(tx)),
        ("rules", "attendance not in {0,1}", bad_att_values, len(att)),
    ]
    summary = pd.DataFrame(summary_rows, columns=["category", "check", "issues", "rows_checked"])
    summary["issue_rate"] = summary.apply(lambda r: pct(int(r["issues"]), int(r["rows_checked"])), axis=1)
    summary.to_csv(SUMMARY_FP, index=False)

    # --- Markdown report ---
    lines = []
    lines.append("# Data Quality Report")
    lines.append("")
    lines.append("## Files checked")
    lines.append(f"- events: `{EVENTS_FP.as_posix()}` → {len(events)} rows")
    lines.append(f"- transactions (sample): `{TX_FP.as_posix()}` → {len(tx)} rows")
    lines.append(f"- attendance (sample): `{ATT_FP.as_posix()}` → {len(att)} rows")
    lines.append("")
    lines.append("## Headline checks")
    lines.append("")
    lines.append("| Category | Check | Issues | Rows | Rate |")
    lines.append("|---|---|---:|---:|---:|")
    for _, r in summary.iterrows():
        lines.append(f"| {r['category']} | {r['check']} | {int(r['issues'])} | {int(r['rows_checked'])} | {r['issue_rate']} |")
    lines.append("")

    # Quick flags
    flags = summary[summary["issues"] > 0]
    if len(flags) == 0:
        lines.append("✅ No issues detected on the sample files.")
    else:
        lines.append("⚠️ Issues detected (sample files). See table above.")
        lines.append("")
        lines.append("### Top issues (sample)")
        for _, r in flags.sort_values("issues", ascending=False).head(6).iterrows():
            lines.append(f"- **{r['check']}** → {int(r['issues'])} issue(s) ({r['issue_rate']})")

    REPORT_FP.write_text("\n".join(lines), encoding="utf-8")

    print("✅ Quality checks done")
    print(f"- {REPORT_FP} (markdown report)")
    print(f"- {SUMMARY_FP} (csv summary)")


if __name__ == "__main__":
    main()
