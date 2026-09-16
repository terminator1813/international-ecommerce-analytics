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
products = query(str(DB), "SELECT * FROM product_summary ORDER BY sales DESC")
line_quality = query(str(DB), "SELECT * FROM completed_line_quality").iloc[0]
summary = query(str(DB), """
    SELECT (SELECT COUNT(*) FROM orders) AS completed_orders,
           (SELECT COUNT(*) FROM customer_360) AS identified_customers,
           (SELECT SUM(order_sales) FROM orders) AS sales,
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
    complete_months = monthly[monthly["is_complete_month"]]
    st.plotly_chart(px.line(complete_months, x="month", y="sales", markers=True,
                            title="Monthly completed sales · full months",
                            labels={"month": "Month", "sales": "Completed sales (£)"}), width="stretch")
    partial_months = monthly[~monthly["is_complete_month"]]
    if not partial_months.empty:
        partial = partial_months.iloc[-1]
        st.caption(
            f"{partial['month']:%B %Y} is incomplete: £{partial['sales']:,.0f} "
            f"through {summary['observation_end']:%d %B %Y}; excluded from the trend."
        )
    st.caption("Business implication: compare sales growth with customer retention before increasing acquisition spend.")

with lifecycle:
    st.subheader("Observed customer segments")
    segment_fig = px.bar(segments, x="lifecycle_segment", y="customers", color="lifecycle_segment",
                         title="Customers by lifecycle segment",
                         labels={"lifecycle_segment": "Segment", "customers": "Customers"})
    segment_fig.update_layout(showlegend=False)
    st.plotly_chart(segment_fig, width="stretch")
    st.dataframe(segments, hide_index=True, width="stretch")
    if not cohorts.empty:
        heat = cohorts.pivot(index="cohort_month", columns="month_number", values="retention_pct")
        heat.index = pd.to_datetime(heat.index).strftime("%Y-%m")
        st.plotly_chart(px.imshow(heat, labels={"x": "Months since first order", "y": "First order month", "color": "Retention %"},
                                title="Monthly cohort retention", aspect="auto", color_continuous_scale="Blues"),
                        width="stretch")
    st.caption("Blank cohort cells have not completed a full calendar month. Segment labels are descriptive; no intervention effect is inferred.")

with market_tab:
    st.subheader("Market opportunity matrix")
    minimum = st.slider("Minimum eligible customers for comparison", 0, 200, 30, 10)
    include_uk = st.checkbox("Include United Kingdom in comparison", value=False,
                             help="The UK accounts for most sales and compresses the scale for other markets.")
    comparable = markets[markets["eligible_customers_90d"] >= minimum].copy()
    if not include_uk:
        comparable = comparable[comparable["country"] != "United Kingdom"]
    if not comparable.empty:
        market_fig = px.scatter(comparable, x="sales", y="repeat_90d_pct",
                                size="eligible_customers_90d", hover_name="country",
                                text="country" if not include_uk else None,
                                title="Completed sales versus 90-day repeat rate",
                                labels={"sales": "Completed sales (£)", "repeat_90d_pct": "90-day repeat (%)"})
        if not include_uk:
            market_fig.update_traces(textposition="top center")
        st.plotly_chart(market_fig, width="stretch")
    else:
        st.info("No markets meet this threshold. Lower the minimum eligible-customer count.")
    st.caption("The comparison excludes the UK by default so smaller markets remain readable; the table below still includes it.")
    st.dataframe(markets, hide_index=True, width="stretch")
    selected_country = st.selectbox("Monthly trend for market", markets["country"].dropna().tolist())
    country_monthly = market_monthly[market_monthly["country"] == selected_country]
    country_complete = country_monthly[country_monthly["is_complete_month"]]
    st.plotly_chart(px.line(country_complete, x="month", y="sales", markers=True,
                            title=f"Monthly completed sales: {selected_country} · full months",
                            labels={"month": "Month", "sales": "Completed sales (£)"}), width="stretch")
    country_partial = country_monthly[~country_monthly["is_complete_month"]]
    if not country_partial.empty:
        partial = country_partial.iloc[-1]
        st.caption(f"{partial['month']:%B %Y} is incomplete (£{partial['sales']:,.0f} through "
                   f"{summary['observation_end']:%d %B %Y}) and excluded from the trend.")
    st.caption("Markets are based on recorded customer countries. Repeat rates use country-specific customer histories and only eligible 90-day windows. Small markets need cautious interpretation.")

with product_tab:
    st.subheader("Top catalog products by completed sales")
    catalog = products[products["product_category"] == "Catalog product"]
    st.plotly_chart(px.bar(catalog.head(10), x="sales", y="description", orientation="h",
                           labels={"sales": "Completed sales (£)", "description": ""}), width="stretch")
    st.dataframe(catalog.head(20).drop(columns="product_category"), hide_index=True, width="stretch")
    excluded = (products[products["product_category"] != "Catalog product"]
                .groupby("product_category", as_index=False)["sales"].sum()
                .sort_values("sales", ascending=False))
    excluded["sales"] = excluded["sales"].round(2)
    st.subheader("Excluded from catalog ranking")
    st.caption("Known shipping, fees, adjustments, gift vouchers, samples and unclassified manual lines remain in completed-sales totals.")
    st.dataframe(excluded, hide_index=True, width="stretch")
    st.subheader("Source record quality")
    st.dataframe(quality, hide_index=True, width="stretch")
    a, b, c = st.columns(3)
    a.metric("Lines without customer ID", f"{int(line_quality['anonymous_lines']):,}")
    b.metric("Sales without customer ID", f"£{line_quality['anonymous_sales']:,.0f}",
             help=f"{100 * line_quality['anonymous_sales'] / sales:.2f}% of completed sales" if sales else None)
    c.metric("Identical-looking excess lines", f"{int(line_quality['duplicate_looking_excess_lines']):,}")
    st.caption(
        f"Missing IDs account for {100 * line_quality['anonymous_sales'] / sales:.2f}% of completed sales "
        f"and are excluded from customer retention and segmentation. Identical-looking lines represent "
        f"£{line_quality['duplicate_looking_sales_exposure']:,.0f} of sales exposure, but may be valid "
        "repeated items; they are not removed or called overstatement. Known cancellations are excluded."
    )
