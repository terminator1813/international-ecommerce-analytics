# Findings and decision note

This is a historical portfolio analysis of UCI Online Retail II (December 2009–December 2011), not a statement about a current business. All values below are generated from the complete two-sheet workbook using the code in this repository.

## What the data shows

1. **Customer value is concentrated.** The top 1% of identified customers account for **31.94%** of identified completed sales. The source includes wholesalers, so this is an account concentration signal rather than evidence about typical individual consumers. A sensible next step for a real retailer would be to distinguish wholesale and consumer accounts before designing loyalty offers.
2. **Repeat behaviour is measurable for a defined population.** **2,484 of 5,281** identified customers with a full 90-day follow-up placed another completed order within 90 days (**47.04%**). The 90-day denominator excludes recent first-time buyers whose full window is not observed. This supports comparing cohorts and markets, but it does not establish why customers returned.
3. **A rule-based retention queue is identifiable.** **291** top-quartile-spend customers had no completed order in the final 90 days of the observation period. Their recorded completed sales total **£1.80m**, or **10.13%** of identified sales. A real team could test a targeted outreach programme against a holdout group; this project does not claim an intervention would recover that revenue.
4. **Market sales are dominated by the UK.** The UK accounts for **85.21%** of completed sales. EIRE records **£664k** from only **5** identified customers, and the Netherlands **£554k** from **22**. High sales in those countries therefore should not be interpreted as broad market demand. Germany and France show 90-day country-level repeat rates of **60.22%** and **55.13%**, but only **93** and **78** eligible customers; these are exploratory comparisons.
5. **Identity coverage constrains customer analysis.** **236,121** completed lines (**22.67%**) lack a customer ID, representing **£3.23m** (**15.40%**) of completed sales. They remain in sales and product totals but are excluded from customer segmentation and retention. The pipeline retains **1,067,371** source lines, classifying **1,041,670** as completed, **19,494** as known cancellation lines and **6,207** as invalid price lines. Completed order sales reconcile to line sales with a **£0.00** gap.
6. **Source-line ambiguity remains visible.** **33,757** excess lines look identical across transaction fields, representing **£496,334.12** (**2.37%**) of completed sales if their extra copies are counted. The source has no line-level business key proving they are errors, so they are retained; this figure is an exposure, **not** a claimed sales overstatement.

## Recommended decisions

- In a live business, first split wholesale and retail customers. Account concentration and high average order values make a single consumer retention strategy misleading.
- Prioritise data capture or identity matching before treating customer retention as a complete view of the business.
- Use the high-value at-risk group as an experiment candidate, with a holdout group and a predeclared success metric such as incremental repeat orders.
- Treat smaller country results as hypotheses for further research. Require a minimum eligible customer count, check account concentration, and compare matched periods before shifting market investment.
- Compare only fully observed months in growth and cohort discussions; December 2011 ends on the 9th and is retained in totals but omitted from full-month trends.

## Boundaries

`Completed sales` excludes known cancellations but cannot perfectly net matched returns against original orders. It includes shipping, fees and unclassified manual entries; the catalog-product ranking excludes those entries under an explicit source-code rule. The source has no product cost, marketing spend, acquisition channel, visit count, shipment origin or verified customer type. Consequently, this project does not calculate profit, return on ad spend, conversion, causal campaign impact or true lifetime value. No raw customer-level dataset or generated database is published here.
