import duckdb
import pandas as pd
import pytest

from src.pipeline import append_frame, build_database, create_model, create_raw_table, normalize
from src.report import export, summarize


def source_frame():
    return pd.DataFrame([
        ["100", "A", "Widget", 2, "2010-01-01", 10.0, 1, "United Kingdom"],
        ["101", "B", "Book", 1, "2010-01-10", 20.0, 1, "United Kingdom"],
        ["102", "A", "Widget", 1, "2010-04-15", 10.0, 1, "United Kingdom"],
        ["103", "C", "Cup", 1, "2010-01-05", 5.0, 2, "France"],
        ["C104", "C", "Cup", -1, "2010-01-06", 5.0, 2, "France"],
        ["105", "D", "Plate", 1, "2010-02-01", 8.0, None, "Germany"],
        ["106", "D", "Plate", -1, "2010-02-02", 8.0, 3, "Germany"],
        ["107", "E", "Vase", 1, "2010-06-01", 0.0, 3, "Germany"],
    ], columns=["Invoice", "StockCode", "Description", "Quantity",
                "InvoiceDate", "Price", "Customer ID", "Country"])


@pytest.fixture
def conn():
    db = duckdb.connect(":memory:")
    create_raw_table(db)
    append_frame(db, source_frame(), "test", 2, 1)
    create_model(db)
    yield db
    db.close()


def test_normalize_keeps_customer_id_missing_and_source_rows():
    result = normalize(source_frame(), "sample", 2, 1)
    assert result.loc[0, "invoice_no"] == "100"
    assert result.loc[5, "customer_id"] is None
    assert result.loc[7, "source_row"] == 9


def test_classification_and_reconciliation(conn):
    summary = summarize(conn)
    assert summary["source_rows"] == 8
    assert summary["completed_lines"] == 5
    assert summary["cancelled_lines"] == 1
    assert summary["invalid_lines"] == 2
    assert summary["sales_gbp"] == 63.0
    assert summary["reconciliation_gap_gbp"] == 0
    assert summary["missing_customer_id_completed_lines"] == 1


def test_customer_repeat_and_cohort_censoring(conn):
    rows = conn.execute("""
        SELECT customer_id, eligible_90d, repeated_90d
        FROM customer_repeat_90d ORDER BY customer_id
    """).fetchall()
    assert rows == [("1", True, 1), ("2", True, 0)]
    assert conn.execute("""
        SELECT retention_pct FROM cohort_retention
        WHERE cohort_month = '2010-01-01' AND month_number = 6
    """).fetchone()[0] is None
    assert conn.execute("""
        SELECT retention_pct FROM cohort_retention
        WHERE cohort_month = '2010-01-01' AND month_number = 0
    """).fetchone()[0] == 100.0


def test_market_repeat_denominator(conn):
    market = conn.execute("""
        SELECT eligible_customers_90d, repeat_customers_90d, repeat_90d_pct
        FROM market_summary WHERE country = 'United Kingdom'
    """).fetchone()
    assert market == (1, 1, 100.0)


def test_missing_required_column():
    with pytest.raises(ValueError, match="Missing required"):
        normalize(pd.DataFrame({"Invoice": ["1"]}), "bad", 2, 1)


def test_csv_end_to_end_and_no_overwrite(tmp_path):
    source = tmp_path / "sample.csv"
    destination = tmp_path / "sample.duckdb"
    source_frame().to_csv(source, index=False)
    assert build_database(source, destination) == 8
    summary = export(destination, tmp_path / "reports")
    assert summary["sales_gbp"] == 63.0
    assert (tmp_path / "reports" / "cohort_retention.csv").is_file()
    with pytest.raises(FileExistsError):
        build_database(source, destination)
