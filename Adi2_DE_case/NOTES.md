# Adi2 LAM | Data Engineering Case — Technical Notes

**Scope:** Colombia (CO), Mexico (MX), Argentina (AR)  
**Business comparison:** Q1 2026 (January–March) versus Q1 2025, in EUR  
**Final source for all business answers:** `data/analytics/fact_sellout_performance.parquet`

## 1. How to run

All commands below are executed **from `Adi2_DE_case/`**. The project uses Python, a local HTTP API, pandas, NumPy, and PyArrow; it does not require a database or cloud service.

### Setup (once)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r api/requirements.txt pandas numpy pyarrow requests
```

### Terminal 1 — start the supplied API

```bash
source .venv/bin/activate
python api/api_server.py
```

The API serves `http://127.0.0.1:8000`. Keep this terminal running. The `/health` endpoint reports the available source counts.

### Terminal 2 — run the full pipeline in one command

```bash
source .venv/bin/activate
python scripts/01_extract.py && python scripts/02_clean.py && python scripts/03_transform.py && python scripts/04_business_analysis.py
```

The `&&` chain stops at the first error, preventing downstream results from being generated from an unsuccessful upstream step. Extraction uses **HTTP requests** and pagination (`limit=2000`, `skip`); it does **not** read the API's internal JSON files as ETL inputs.

To open the leadership presentation on macOS:

```bash
open outputs/business/leadership_presentation.html
```

Individual stages can also be run in sequence when troubleshooting. Running `04_business_analysis.py` alone requires an existing validated final Parquet; it **only reads that fact table** for its metrics, tables, and HTML.

## 2. Deliverables and data flow

| Location | Purpose |
|---|---|
| `scripts/01_extract.py` | Fetch all five local API endpoints and perform a non-destructive initial data-quality review |
| `data/raw/*.json` | Original API responses, preserved without cleaning (locally reproducible; may be excluded from Git) |
| `outputs/eda/` | Initial data profiling, anomalies, and inspection tables |
| `scripts/02_clean.py` | Standardize each source, repair validated errors, retain transaction-level audit flags |
| `data/clean/*.parquet` | One cleaned Parquet per source (five files) |
| `data/clean/cleaning_summary.csv` | Count of transformations and flagged events |
| `scripts/03_transform.py` | Join reference data, convert to EUR, apply channel attribution, and build the aggregated fact |
| `data/analytics/fact_sellout_performance.parquet` | **Official final fact table** |
| `outputs/audit/reconciliation_steps.csv` | Source-to-fact bridge by channel, including exclusions and transfers |
| `outputs/audit/reconciliation_by_channel.csv` | Final EUR and units reconciliation |
| `scripts/04_business_analysis.py` | Calculate Q1 comparisons and render leadership HTML using **only the final fact** |
| `outputs/business/leadership_presentation.html` | Offline leadership presentation with charts, evidenced insights, answers, and strategies |
| `outputs/business/*.csv` | Supporting aggregates derived solely from the final fact |

**Grain of the fact:** one row per `month × country × channel × store_spot × group_article × fulfilled_by_store_flag`. Consequently, a fact row is **not** an individual ticket or order. Multiple transaction lines for the same month, country, reporting channel, store, article, and fulfillment flag are aggregated into one row. ECOM orders served from a distribution center have no associated `store_spot`; those null keys are retained during grouping (`dropna=False`). Store codes remain strings to preserve leading zeroes.

Measures include `gross_qty`, `return_qty`, `net_qty`, `gross_sales_eur`, `return_sales_eur`, and `net_sales_eur`. Extra reference attributes (store, category, division) are retained for business analysis.

## 3. Data profiling and cleaning decisions

The API `/health` counts were reconciled with the fully paginated extraction.

| API source | Extracted rows | Clean rows |
|---|---:|---:|
| Retail sales | 4,456 | 4,456 |
| ECOM sales | 3,523 | 3,523 |
| Stores | 12 | 12 |
| Articles | 150 | 150 |
| FX rates | 3 | 3 |
| **Total** | **8,144** | **8,144** |

**No rows are removed at the clean layer.** The following issues and handling rules were documented:

| Finding | Quantified impact | Decision / justification |
|---|---:|---|
| Retail accounting dates use mixed `YYYY-MM-DD` and `DD/MM/YYYY` conventions | **394** rows in the alternative format | Parse each explicitly into `datetime`; avoid ambiguous month/day interpretation. Use `calendar_date`, not order-placement date, for reporting. |
| Retail `sold_qty` includes non-numeric `N/A` | **15** rows | Reconstruct deterministically as `net_qty + return_qty`, only on validated sale rows with zero returns; flag `sold_qty_reconstructed`. No mean/median imputation. |
| Retail `net_sales` contains letter `O` instead of digit `0` | **18** rows | Perform constrained, pattern-validated replacement `O → 0`, then cast to numeric; flag `net_sales_repaired`. The original amount is monetary, not a quantity. |
| Return measures missing on ordinary sales | Present in both sources | Interpret missing `return_qty` / `return_value` as **zero only where transaction semantics support it**; do not indiscriminately fill all missing fields. |
| Return transaction lines | **145 Retail + 299 ECOM = 444** rows | Retain as valid business events, reducing quantities and sales on **accounting date**; do not deduct `return_value` a second time from an already-negative `net_sales`. |
| Reversal indicator `X` and linked original sales | **71 Retail + 15 ECOM = 86** reversal lines; **86** linked original lines | Match references and supporting line attributes; flag both the reversal and its original as voided. Exclude **172** lines when computing valid commercial sales, but retain the rows in the clean data for traceability. |
| ECOM orders fulfilled by own stores | **420** raw ECOM lines; **418** valid after void exclusions | Report as **RETAIL**, retaining `fulfilled_by_store_flag=True`. DC-fulfilled online orders remain **ECOM**. |
| Store-fulfilled online orders need store master attribution | Store codes on applicable rows | Join on **country + store_spot**, validating a many-to-one match and preventing duplicated rows. Storeless ECOM records remain null by design. |

No blanket duplicate deletion or outlier removal was applied. Source profiling found no exact duplicate rows; business keys and master uniqueness are checked explicitly. The fixed FX rates supplied by Adi2 are **COP 4,500/EUR; MXN 20/EUR; ARS 1,000/EUR**. For each line, `sales_eur = sales_local / units_per_eur`. Rates are constant across both periods; amounts exclude VAT.

**Accounting assumptions:** `net_qty = sold_qty − return_qty`; `net_sales = gross_sales − return_value`. Returns have negative net values in the source; gross and return components are derived consistently and reconciled against the source net amounts. Reversal lines marked `X` in this extract do not reliably carry a negative sign, so simply summing them or dropping only the `X` row would overstate sales; both members of each validated void pair are excluded from the final commercial population.

## 4. Transformation and auditable reconciliation

**Join validations:** all three joins (FX, Stores, Articles) preserved **7,979 → 7,979** transaction lines. Local sales totals before/after each join were unchanged. Before excluding voids, the combined source total was **€679,828.30**.

The table below reproduces the signed reconciliation in `outputs/audit/reconciliation_steps.csv`; amounts and units are for the **full extracted dataset (both years)**, not an individual quarter.

| Step / contribution | Channel | Lines | Net units | Net sales EUR |
|---|---|---:|---:|---:|
| Clean source | Retail | 4,456 | 5,140 | €397,121.00 |
| Clean source | ECOM | 3,523 | 3,628 | €282,707.30 |
| Exclude validated voided lines | Retail | −142 | −162 | −€11,907.60 |
| Exclude validated voided lines | ECOM | −30 | −32 | −€1,851.40 |
| Transfer store-fulfilled online orders **out of ECOM** | ECOM | −418 | −437 | −€32,986.50 |
| Transfer same orders **into Retail** | Retail | +418 | +437 | +€32,986.50 |
| **Final fact** | **Retail** | **4,732 source lines attributed** | **5,415** | **€418,199.90** |
| **Final fact** | **ECOM** | **3,075 source lines attributed** | **3,159** | **€247,869.40** |
| **Final combined total** | **All** | **7,807 valid source lines** | **8,574** | **€666,069.30** |

The void adjustment is **€13,759.00** in total (`€679,828.30 − €666,069.30`), equivalent to **2.02%** of clean-source net EUR. The store-fulfillment reclassification moves **418 lines / 437 net units / €32,986.50** between reporting channels but has **zero effect** on overall net sales.

**Validation results:**

- No unintentional row multiplication/loss or sales movement across the three `many_to_one` joins.
- Matched reference keys for FX, articles, and stores with valid store identifiers; no unexplained unmatched business keys.
- Final fact has **5,579 unique grain rows** after aggregating 7,807 valid lines.
- `gross_qty − return_qty = net_qty` and `gross_sales_eur − return_sales_eur = net_sales_eur` hold within the specified numeric tolerance.
- By-channel source-to-fact reconciliation: **€0.00 difference and 0 units difference** for both Retail and ECOM.

## 5. Business interpretation — Q1 2026 vs. Q1 2025

The business report is calculated **exclusively from the final fact**, not from raw or cleaned transactional files.

| Reporting channel | Q1 2025 EUR | Q1 2026 EUR | Change EUR | Growth |
|---|---:|---:|---:|---:|
| Retail | €203,110.20 | €215,089.70 | +€11,979.50 | +5.90% |
| ECOM | €115,876.00 | €131,993.40 | +€16,117.40 | +13.91% |
| **LAM total** | **€318,986.20** | **€347,083.10** | **+€28,096.90** | **+8.81%** |

ECOM grows faster, but Retail also grows. Physical shop-floor sales decreased **€14,911.40 (−7.45%)**, while online orders fulfilled by stores rose **€26,890.90**. The share of **online-originated net EUR shipped by stores** increased from **2.56% (Q1 2025)** to **18.49% (Q1 2026)**. This share is based on monetary sales, **not the number of individual orders**, because the fact is aggregated and does not retain order IDs.

| Country | Q1 2026 net sales EUR | Year-over-year growth | Change EUR |
|---|---:|---:|---:|
| Mexico | €162,692.20 | +5.18% | +€8,016.10 |
| Colombia | €108,097.70 | +15.48% | +€14,487.60 |
| Argentina | €76,293.20 | +7.91% | +€5,593.20 |

**Mexico is the largest market by absolute sales; Colombia is the largest contributor to growth** (51.56% of the LAM net increase). In Colombia, Footwear contributed **+€14,343.30** and online-originated activity grew, while physical in-store sales declined **€589.10**. Product and origin splits are *alternative views of the same sales* and must not be added together.

The main store drivers include **Adi2 Store Unicentro (Colombia, +€9,930.20)**, of which **+€6,882.30** came from online orders shipped by the store, versus declines at **Adi2 Brand Center Andares (Mexico, −€3,067.40)** and **Adi2 Outlet Oviedo (Colombia, −€2,380.10)**.

Additional observations: Footwear contributed **+€21,633.40** (~77.0% of regional net growth). Retail's **monetary return ratio** (`return_sales_eur / gross_sales_eur`) increased from **2.79% to 4.41%** (+1.62 percentage points). This is not an order-based return rate.

**Decision framing:** leadership's hypothesis is **partially** supported: online-originated shopping is growing, but stores still contribute as fulfillment locations. The evidence measures net sales, **not profit or ROI**. It cannot establish causes such as marketing spend, customer preference, rents, fulfillment cost, or inventory availability. Proposed strategies in the HTML—omnichannel pilots, targeted store recovery/returns control, and market/product investment tests—require additional cost and margin information before commitment.

## 6. AI use and verification

ChatGPT was used to assist with ETL structure, data-quality rules, validation checks, business aggregations, and the HTML presentation. Outputs were checked against the API `/health` counts, inspected data-quality exceptions, executed Python validations, before/after join totals, and a channel-level bridge with **zero residual difference** in EUR and net units; proposed interpretations were distinguished from causal claims.

## 7. Limitations and next checks

- Fixed FX rates are supplied by the case and do not model historical currency fluctuations.
- The fact's grain cannot support unique-order counts, conversion rates, store visit traffic, or customer-level analysis.
- Store fulfillment attribution follows Adi2's accounting rule. It is not the same as the consumer's original online shopping channel.
- Return reasons and operating economics were not provided. Validate hypotheses with operational, margin, and inventory data before changing investment allocations.
- For a full rerun after cloning, ensure the supplied local API can be started; `data/raw/` may not be committed to Git, because it is generated from API calls.
