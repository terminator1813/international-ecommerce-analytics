"""Export aggregate tables and an auditable metric summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from .pipeline import DEFAULT_DB, ROOT


TABLES = {
    "quality_by_status": "SELECT record_status, COUNT(*) AS lines FROM classified_lines GROUP BY 1 ORDER BY 1",
    "monthly_sales": "SELECT * FROM monthly_sales ORDER BY month",
    "market_summary": "SELECT * FROM market_summary ORDER BY sales DESC",
    "market_monthly": "SELECT * FROM market_monthly ORDER BY country, month",
    "cohort_retention": "SELECT * FROM cohort_retention ORDER BY cohort_month, month_number",
    "product_summary": "SELECT * FROM product_summary ORDER BY sales DESC",
    "completed_line_quality": "SELECT * FROM completed_line_quality",
    "customer_segments": "SELECT lifecycle_segment, COUNT(*) AS customers, SUM(observed_sales) AS sales FROM customer_360 GROUP BY 1 ORDER BY sales DESC",
}


def summarize(conn: duckdb.DuckDBPyConnection) -> dict:
    """Use invoice and customer denominators defined in the SQL model."""
    scalar = lambda query: conn.execute(query).fetchone()[0]
    raw = scalar("SELECT COUNT(*) FROM raw_lines")
    completed = scalar("SELECT COUNT(*) FROM completed_lines")
    invalid = scalar("SELECT COUNT(*) FROM classified_lines WHERE record_status LIKE 'invalid%'")
    cancelled = scalar("SELECT COUNT(*) FROM classified_lines WHERE record_status = 'cancelled'")
    unknown_customer, anonymous_sales, duplicate_lines, duplicate_sales = conn.execute("""
        SELECT anonymous_lines, anonymous_sales, duplicate_looking_excess_lines,
               duplicate_looking_sales_exposure
        FROM completed_line_quality
    """).fetchone()
    if completed + invalid + cancelled != raw:
        raise ValueError("Line classifications do not cover every source row")
    invoices = scalar("SELECT COUNT(*) FROM orders")
    cancellation_invoices = scalar(
        "SELECT COUNT(DISTINCT invoice_no) FROM classified_lines WHERE record_status = 'cancelled'"
    )
    eligible, repeat = conn.execute("""
        SELECT COUNT(*) FILTER (WHERE eligible_90d),
               COUNT(*) FILTER (WHERE eligible_90d AND repeated_90d = 1)
        FROM customer_repeat_90d
    """).fetchone()
    sales = scalar("SELECT COALESCE(SUM(order_sales), 0) FROM orders")
    line_sales = scalar("SELECT COALESCE(SUM(line_sales), 0) FROM completed_lines")
    if abs(float(sales) - float(line_sales)) > 0.01:
        raise ValueError("Order sales do not reconcile to completed line sales")
    return {
        "source_rows": raw,
        "completed_lines": completed,
        "cancelled_lines": cancelled,
        "invalid_lines": invalid,
        "missing_customer_id_completed_lines": unknown_customer,
        "missing_customer_id_completed_lines_pct": round(100 * unknown_customer / completed, 2) if completed else None,
        "missing_customer_id_sales_gbp": float(anonymous_sales),
        "missing_customer_id_sales_pct": round(100 * float(anonymous_sales) / float(sales), 2) if sales else None,
        "duplicate_looking_excess_lines": int(duplicate_lines),
        "duplicate_looking_sales_exposure_gbp": float(duplicate_sales),
        "duplicate_looking_sales_exposure_pct": round(100 * float(duplicate_sales) / float(sales), 2) if sales else None,
        "completed_orders": invoices,
        "identified_customers": scalar("SELECT COUNT(*) FROM customer_360"),
        "sales_gbp": float(sales),
        "average_order_value_gbp": round(float(sales) / invoices, 2) if invoices else None,
        "known_cancellation_invoices": cancellation_invoices,
        "known_cancellation_invoice_rate_pct": round(
            100 * cancellation_invoices / (invoices + cancellation_invoices), 2
        ) if invoices + cancellation_invoices else None,
        "repeat_90d_eligible_customers": eligible,
        "repeat_90d_customers": repeat,
        "repeat_90d_rate_pct": round(100 * repeat / eligible, 2) if eligible else None,
        "observation_end": str(scalar("SELECT MAX(invoice_at) FROM raw_lines")),
        "reconciliation_gap_gbp": round(float(sales) - float(line_sales), 2),
    }


def export(db: Path, out: Path) -> dict:
    if not db.is_file():
        raise FileNotFoundError(db)
    out.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db), read_only=True)
    try:
        summary = summarize(conn)
        for name, query in TABLES.items():
            conn.execute(query).df().to_csv(out / f"{name}.csv", index=False)
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return summary
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    print(json.dumps(export(args.db, args.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
