"""Decision-oriented view of the UCI Online Retail II analysis."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.getenv("RETAIL_DB_PATH", str(ROOT / "data" / "retail.duckdb")))

st.set_page_config(page_title="International E-commerce Analytics", layout="wide")
st.title("International E-commerce Analytics")
st.caption("Customer lifecycle, market performance, and data quality · UCI Online Retail II")

if not DB.is_file():
    st.info("Build the analytical database first: `python -m src.pipeline --input data/online_retail_II.xlsx`")
    st.stop()


@st.cache_data(show_spinner=False)
def query(db_path: str, sql: str) -> pd.DataFrame:
    conn = duckdb.connect(db_path, read_only=True)
    try:
        return conn.execute(sql).df()
    finally:
        conn.close()


quality = query(str(DB), """
    SELECT record_status, COUNT(*) AS lines FROM classified_lines GROUP BY 1 ORDER BY 1
""")
monthly = query(str(DB), "SELECT * FROM monthly_sales ORDER BY month")
markets = query(str(DB), "SELECT * FROM market_summary ORDER BY sales DESC")
market_monthly = query(str(DB), "SELECT * FROM market_monthly ORDER BY country, month")
segments = query(str(DB), """
    SELECT lifecycle_segment, COUNT(*) AS customers, SUM(observed_sales) AS observed_sales
    FROM customer_360 GROUP BY 1 ORDER BY observed_sales DESC
""")
cohorts = query(str(DB), "SELECT * FROM cohort_retention WHERE month_number <= 6 ORDER BY cohort_month, month_number")
products = query(str(DB), "SELECT * FROM product_summary ORDER BY sales DESC LIMIT 20")
summary = query(str(DB), """
    SELECT (SELECT COUNT(*) FROM orders) AS completed_orders,
           (SELECT COUNT(*) FROM customer_360) AS identified_customers,
           (SELECT SUM(order_sales) FROM orders) AS sales,
           (SELECT COUNT(*) FROM completed_lines WHERE customer_id IS NULL) AS anonymous_lines,
           (SELECT MAX(invoice_at) FROM raw_lines) AS observation_end
""").iloc[0]
repeat = query(str(DB), """
    SELECT COUNT(*) FILTER (WHERE eligible_90d) AS eligible,
           COUNT(*) FILTER (WHERE eligible_90d AND repeated_90d = 1) AS repeated
    FROM customer_repeat_90d
""").iloc[0]

st.caption(f"Observation ends {summary['observation_end']:%Y-%m-%d}. Monetary values are GBP; prices are sales, not profit.")
overview, lifecycle, market_tab, product_tab = st.tabs(
    ["Overview", "Customer lifecycle", "Markets", "Products & quality"]
)

with overview:
    sales = float(summary["sales"] or 0)
    orders = int(summary["completed_orders"] or 0)
    customers = int(summary["identified_customers"] or 0)
    eligible = int(repeat["eligible"] or 0)
    repeated = int(repeat["repeated"] or 0)
    a, b, c, d = st.columns(4)
    a.metric("Completed sales", f"£{sales:,.0f}")
    b.metric("Completed orders", f"{orders:,}")
    c.metric("Identified customers", f"{customers:,}")
    d.metric("90-day repeat", f"{100 * repeated / eligible:.1f}%" if eligible else "N/A",
             help=f"{repeated:,} of {eligible:,} customers with a full 90-day follow-up")
    st.plotly_chart(px.line(monthly, x="month", y="sales", markers=True,
                            title="Monthly completed sales"), width="stretch")
    st.caption("Business implication: compare sales growth with customer retention before increasing acquisition spend.")

with lifecycle:
    st.subheader("Observed customer segments")
    st.plotly_chart(px.bar(segments, x="lifecycle_segment", y="customers", color="lifecycle_segment",
                           title="Customers by lifecycle segment"), width="stretch")
    st.dataframe(segments, hide_index=True, width="stretch")
    if not cohorts.empty:
        heat = cohorts.pivot(index="cohort_month", columns="month_number", values="retention_pct")
        heat.index = pd.to_datetime(heat.index).strftime("%Y-%m")
        st.plotly_chart(px.imshow(heat, labels={"x": "Months since first order", "y": "First order month", "color": "Retention %"},
                                title="Monthly cohort retention", aspect="auto", color_continuous_scale="Blues"),
                        width="stretch")
    st.caption("Blank cohort cells have not completed the observation window. Segment labels are descriptive; no intervention effect is inferred.")

with market_tab:
    st.subheader("Market opportunity matrix")
    minimum = st.slider("Minimum eligible customers for comparison", 0, 200, 30, 10)
    comparable = markets[markets["eligible_customers_90d"] >= minimum].copy()
    if not comparable.empty:
        st.plotly_chart(px.scatter(comparable, x="sales", y="repeat_90d_pct",
                                   size="eligible_customers_90d", hover_name="country",
                                   title="Completed sales versus 90-day repeat rate",
                                   labels={"sales": "Completed sales (£)", "repeat_90d_pct": "90-day repeat (%)"}),
                        width="stretch")
    st.dataframe(markets, hide_index=True, width="stretch")
    selected_country = st.selectbox("Monthly trend for market", markets["country"].dropna().tolist())
    country_monthly = market_monthly[market_monthly["country"] == selected_country]
    st.plotly_chart(px.line(country_monthly, x="month", y="sales", markers=True,
                            title=f"Monthly completed sales: {selected_country}"), width="stretch")
    st.caption("Markets are based on recorded customer countries. Repeat rates use country-specific customer histories and only eligible 90-day windows. Small markets need cautious interpretation.")

with product_tab:
    st.subheader("Top products by completed sales")
    st.plotly_chart(px.bar(products.head(10), x="sales", y="description", orientation="h",
                           title="Top 10 products by sales"), width="stretch")
    st.dataframe(products, hide_index=True, width="stretch")
    st.subheader("Source record quality")
    st.dataframe(quality, hide_index=True, width="stretch")
    st.metric("Completed lines without customer ID", f"{int(summary['anonymous_lines']):,}")
    st.caption("Missing customer IDs remain in sales totals but are excluded from customer retention and segmentation. Known cancellation lines are excluded from completed sales.")
