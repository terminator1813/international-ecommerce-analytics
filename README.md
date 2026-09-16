# International E-commerce Customer Lifecycle & Market Growth Analytics

An end-to-end, reproducible analysis of the [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) transactions. It answers three questions: which customers purchase again, how customer behaviour varies by country, and which source-data limitations matter for those decisions.

The project uses SQL in DuckDB for the analytical model, Python for ingestion and checks, and Streamlit for exploration. The source is an historical UK online retailer dataset, **not current market performance**. Customer country is a market proxy; shipping routes, acquisition channels, marketing cost and product costs are not present.

**Verified result:** 1,067,371 source lines, 40,077 completed order groups and £20.97m completed sales; 90-day repeat was 47.04% among 5,281 eligible identified customers. See the [findings and decision note](docs/findings.md) for scope and caveats.

## Reproduce the analysis

Requires Python 3.11 or newer. Download `online_retail_II.xlsx` from [UCI](https://archive.ics.uci.edu/dataset/502/online+retail+ii) into `data/`; the file is not included in this repository. Both workbook sheets are loaded.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.pipeline --input data/online_retail_II.xlsx --db data/retail.duckdb
python -m src.report --db data/retail.duckdb --out reports
streamlit run dashboard/app.py
python -m pytest -q
```

The loader accepts an equivalent `.csv` as well. It refuses to overwrite an existing database. To rebuild, choose a new `--db` path. To point the dashboard at a different database, set `RETAIL_DB_PATH`.

## Analytical model

| View | Grain | Use |
| --- | --- | --- |
| `classified_lines` | Source row | Explicit completed, cancelled, and invalid status |
| `completed_lines` | Valid positive order line | Sales and product calculations |
| `orders` | Invoice, customer ID, country | Completed order count and average order value |
| `customer_360` | Identified customer | First/last purchase, observed sales, lifecycle segment |
| `customer_repeat_90d` | Identified customer | 90-day repeat with a full follow-up window |
| `cohort_retention` | First-purchase month × elapsed month | Monthly customer retention, with unobserved months null |
| `market_summary` | Recorded country | Sales, eligible customers, repeat and known cancellations |
| `monthly_sales` / `market_monthly` | Month / country × month | Total and market sales trends |
| `product_summary` | Product | Merchandising view |

The full SQL is in [`sql/model.sql`](sql/model.sql). The pipeline does not remove identical looking line items because repeated order lines may be valid; every source row is retained with a sheet and row number.

### Metric definitions

- **Completed sales** = sum of positive quantity × positive price for non-cancellation invoices with required fields. This is gross completed sales, **not profit** or net revenue after matched returns.
- **Completed order** = one `(invoice_no, customer_id, country)` group. The report reconciles order sales to line sales.
- **90-day repeat rate** = identified customers with another completed order within 90 days of their first order ÷ identified customers whose first order was at least 90 days before the final observed transaction. The market view calculates this within each country.
- **Cohort monthly retention** = customers active in elapsed month ÷ customers who first purchased in the cohort month. Months beyond the observed data end are null, not zero.
- **Known cancellation invoice rate** = distinct `C` prefixed invoices ÷ (completed order groups + distinct `C` prefixed invoices). It is an observable proxy because cancellation lines cannot always be matched to original invoices. Negative quantities without a `C` prefix are excluded as invalid, not silently netted.
- **Customer value** = observed completed sales over the dataset period. It is not a forecast of lifetime value.
- **High-value at risk** = observed sales in the top quartile and at least 90 days since last purchase at the dataset cutoff. This is a descriptive rule, not a validated churn prediction.

Lines without a customer ID contribute to sales and product totals but cannot enter customer or cohort metrics. Line statuses and missing ID counts are shown in the dashboard and `reports/summary.json`.

## Dashboard

The four pages cover completed sales, RFM-based customer lifecycle segments, a market opportunity matrix, and product/data quality. The market scatter compares sales with 90-day repeat rate and lets you set a minimum eligible-customer count; a separate chart shows each market's monthly sales history. It avoids a weighted opportunity score whose weights cannot be validated from this data alone.

## Quality controls

`src.report` checks that completed line sales reconcile to completed order sales. Tests cover source schema normalization, missing customer IDs, cancellation and invalid-row classification, observation-window censoring, cohort behaviour, and market repeat denominators. GitHub Actions runs tests on every push and pull request using a small synthetic fixture; the full UCI workbook is not needed in CI.

## Source and limitations

Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning Repository. [DOI: 10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D). Source data licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The dataset covers December 2009 to December 2011 and includes wholesalers, so individual consumer marketing interpretations need care. It lacks costs, marketing channels, site visits and verified shipping routes. Country comparisons are descriptive and can be unstable for small customer groups. The dashboard does not expose individual customer IDs.

## Repository map

```text
src/pipeline.py       Read workbook/CSV in chunks and build DuckDB
sql/model.sql         Analytical views and metric definitions
src/report.py         Reconciliation, quality summary, aggregate exports
dashboard/app.py      Streamlit dashboard
tests/test_pipeline.py Synthetic edge-case tests
data/README.md        Dataset download and attribution
docs/findings.md       Verified aggregate results and decisions
```
