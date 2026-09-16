CREATE OR REPLACE VIEW classified_lines AS
SELECT *,
    CASE
        WHEN invoice_no IS NULL OR invoice_at IS NULL OR stock_code IS NULL OR country IS NULL
             OR quantity IS NULL OR unit_price IS NULL THEN 'invalid_missing'
        WHEN unit_price <= 0 THEN 'invalid_price'
        WHEN starts_with(upper(invoice_no), 'C') THEN 'cancelled'
        WHEN quantity <= 0 THEN 'invalid_quantity'
        ELSE 'completed'
    END AS record_status
FROM raw_lines;

CREATE OR REPLACE VIEW completed_lines AS
SELECT *, CAST(quantity * unit_price AS DECIMAL(18, 2)) AS line_sales
FROM classified_lines
WHERE record_status = 'completed';

-- An invoice can contain many lines. Country and customer are kept in the
-- key so conflicting source records are visible rather than silently merged.
CREATE OR REPLACE VIEW orders AS
SELECT invoice_no, customer_id, country,
       MIN(invoice_at) AS order_at,
       CAST(SUM(line_sales) AS DECIMAL(18, 2)) AS order_sales,
       SUM(quantity) AS units,
       COUNT(*) AS line_count
FROM completed_lines
GROUP BY invoice_no, customer_id, country;

CREATE OR REPLACE VIEW identified_orders AS
SELECT * FROM orders WHERE customer_id IS NOT NULL;

CREATE OR REPLACE VIEW customer_360 AS
WITH base AS (
    SELECT customer_id,
           ARG_MIN(country, order_at) AS first_country,
           MIN(order_at) AS first_order_at,
           MAX(order_at) AS last_order_at,
           COUNT(*) AS order_count,
           CAST(SUM(order_sales) AS DECIMAL(18, 2)) AS observed_sales,
           CAST(AVG(order_sales) AS DECIMAL(18, 2)) AS avg_order_value
    FROM identified_orders
    GROUP BY customer_id
), ranked AS (
    SELECT *, QUANTILE_CONT(observed_sales, 0.75) OVER () AS sales_p75,
           (SELECT MAX(invoice_at) FROM raw_lines) AS observation_end
    FROM base
)
SELECT customer_id, first_country, first_order_at, last_order_at,
       order_count, observed_sales, avg_order_value,
       DATE_DIFF('day', CAST(last_order_at AS DATE), CAST(observation_end AS DATE)) AS recency_days,
       CASE
           WHEN observed_sales >= sales_p75 AND
                DATE_DIFF('day', CAST(last_order_at AS DATE), CAST(observation_end AS DATE)) >= 90
                THEN 'High-value at risk'
           WHEN observed_sales >= sales_p75 AND order_count >= 3 THEN 'High-value loyal'
           WHEN order_count = 1 AND first_order_at >= observation_end - INTERVAL 30 DAY THEN 'New one-time'
           WHEN order_count >= 2 THEN 'Repeat customer'
           ELSE 'One-time customer'
       END AS lifecycle_segment
FROM ranked;

-- Only customers whose first order has a full 90-day follow-up are eligible.
CREATE OR REPLACE VIEW customer_repeat_90d AS
WITH firsts AS (
    SELECT customer_id, MIN(order_at) AS first_order_at
    FROM identified_orders GROUP BY customer_id
), followup AS (
    SELECT f.customer_id, f.first_order_at,
           MAX(CASE WHEN o.order_at > f.first_order_at
                     AND o.order_at <= f.first_order_at + INTERVAL 90 DAY
                    THEN 1 ELSE 0 END) AS repeated_90d
    FROM firsts f JOIN identified_orders o USING (customer_id)
    GROUP BY f.customer_id, f.first_order_at
)
SELECT *, first_order_at <= (SELECT MAX(invoice_at) FROM raw_lines) - INTERVAL 90 DAY
           AS eligible_90d
FROM followup;

CREATE OR REPLACE VIEW cohort_retention AS
WITH firsts AS (
    SELECT customer_id, DATE_TRUNC('month', MIN(order_at)) AS cohort_month
    FROM identified_orders GROUP BY customer_id
), activity AS (
    SELECT DISTINCT f.customer_id, f.cohort_month,
           DATE_TRUNC('month', o.order_at) AS activity_month,
           DATE_DIFF('month', f.cohort_month, DATE_TRUNC('month', o.order_at)) AS month_number
    FROM firsts f JOIN identified_orders o USING (customer_id)
), sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size FROM firsts GROUP BY cohort_month
), months AS (
    SELECT cohort_month, month_number
    FROM sizes CROSS JOIN GENERATE_SERIES(0, 11) AS t(month_number)
)
SELECT m.cohort_month, m.month_number, s.cohort_size,
       CASE WHEN DATE_TRUNC('month', (SELECT MAX(invoice_at) FROM raw_lines))
                      < m.cohort_month + m.month_number * INTERVAL 1 MONTH
            THEN NULL
            ELSE COUNT(DISTINCT a.customer_id) END AS active_customers,
       CASE WHEN DATE_TRUNC('month', (SELECT MAX(invoice_at) FROM raw_lines))
                      < m.cohort_month + m.month_number * INTERVAL 1 MONTH
            THEN NULL
            ELSE ROUND(COUNT(DISTINCT a.customer_id) * 100.0 / s.cohort_size, 2)
       END AS retention_pct
FROM months m JOIN sizes s USING (cohort_month)
LEFT JOIN activity a ON a.cohort_month = m.cohort_month AND a.month_number = m.month_number
GROUP BY m.cohort_month, m.month_number, s.cohort_size;

CREATE OR REPLACE VIEW market_customer_repeat AS
WITH firsts AS (
    SELECT country, customer_id, MIN(order_at) AS first_order_at
    FROM identified_orders GROUP BY country, customer_id
), repeat_status AS (
    SELECT f.country, f.customer_id, f.first_order_at,
           MAX(CASE WHEN o.order_at > f.first_order_at
                     AND o.order_at <= f.first_order_at + INTERVAL 90 DAY
                    THEN 1 ELSE 0 END) AS repeated_90d
    FROM firsts f JOIN identified_orders o
      ON f.country = o.country AND f.customer_id = o.customer_id
    GROUP BY f.country, f.customer_id, f.first_order_at
)
SELECT country, COUNT(*) AS identified_customers,
       COUNT(*) FILTER (WHERE first_order_at <= (SELECT MAX(invoice_at) FROM raw_lines) - INTERVAL 90 DAY)
           AS eligible_customers_90d,
       COUNT(*) FILTER (WHERE repeated_90d = 1 AND
                             first_order_at <= (SELECT MAX(invoice_at) FROM raw_lines) - INTERVAL 90 DAY)
           AS repeat_customers_90d
FROM repeat_status GROUP BY country;

CREATE OR REPLACE VIEW market_summary AS
WITH sales AS (
    SELECT country, COUNT(*) AS completed_orders,
           CAST(SUM(order_sales) AS DECIMAL(18, 2)) AS sales,
           CAST(AVG(order_sales) AS DECIMAL(18, 2)) AS avg_order_value
    FROM orders GROUP BY country
), cancels AS (
    SELECT country, COUNT(DISTINCT invoice_no) AS cancellation_invoices,
           CAST(SUM(ABS(quantity * unit_price)) AS DECIMAL(18, 2)) AS cancellation_value
    FROM classified_lines WHERE record_status = 'cancelled' GROUP BY country
)
SELECT s.country, s.completed_orders, s.sales, s.avg_order_value,
       COALESCE(r.identified_customers, 0) AS identified_customers,
       COALESCE(r.eligible_customers_90d, 0) AS eligible_customers_90d,
       COALESCE(r.repeat_customers_90d, 0) AS repeat_customers_90d,
       CASE WHEN r.eligible_customers_90d > 0
            THEN ROUND(r.repeat_customers_90d * 100.0 / r.eligible_customers_90d, 2)
            ELSE NULL END AS repeat_90d_pct,
       COALESCE(c.cancellation_invoices, 0) AS cancellation_invoices,
       COALESCE(c.cancellation_value, 0) AS cancellation_value
FROM sales s LEFT JOIN market_customer_repeat r USING (country)
LEFT JOIN cancels c USING (country);

CREATE OR REPLACE VIEW monthly_sales AS
SELECT DATE_TRUNC('month', order_at) AS month, COUNT(*) AS orders,
       CAST(SUM(order_sales) AS DECIMAL(18, 2)) AS sales
FROM orders GROUP BY 1;

CREATE OR REPLACE VIEW market_monthly AS
SELECT country, DATE_TRUNC('month', order_at) AS month, COUNT(*) AS orders,
       CAST(SUM(order_sales) AS DECIMAL(18, 2)) AS sales
FROM orders GROUP BY country, month;

CREATE OR REPLACE VIEW product_summary AS
SELECT stock_code, ARG_MAX(description, invoice_at) AS description,
       COUNT(DISTINCT invoice_no) AS orders, SUM(quantity) AS units,
       CAST(SUM(line_sales) AS DECIMAL(18, 2)) AS sales
FROM completed_lines GROUP BY stock_code;
