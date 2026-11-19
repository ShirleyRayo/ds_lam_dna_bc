# Adi2 — Data Engineer Technical Assessment

## On-site case: From Raw Sources to a Business Answer

| | |
|---|---|
| Duration | **2 h 20 min**: 2 hours to solve the case + 20 minutes to present it |
| Stack | Your laptop, Python, local files |
| Data | Local API, included in this package |

---

## 1. Context

**Adi2** is a sporting goods brand that sells to end consumers in **Colombia, Mexico and Argentina** through two own channels:

- **Retail:** own physical stores.
- **ECOM:** own online store.

Each channel has its own source system, so sales arrive through different sources with different structures. There are also a store master, an article master and an exchange rate table.

**How the business operates**

- Since 2025, besides selling on the shop floor, own stores also pick, pack and ship orders placed in the online store, and the service has been rolled out to more stores. That sale is assigned to **Retail**, because it comes out of the store's inventory. Store managers are evaluated on all the sales that leave their store.
- When a consumer returns a product, the return is recorded on the date it happens and is **deducted** from sales: net sales = sales − returns.
- A voided transaction (for example, a corrected cashier error) does not represent a sale.

**Currency**

- Each country records its sales in its own local currency: Colombia in **COP**, Mexico in **MXN** and Argentina in **ARS**. Amounts exclude VAT.
- To compare countries and channels, the company converts everything to **EUR** using a **fixed, predefined exchange rate** per currency (provided by the API). The same rate applies to the whole period.

> Make reasonable assumptions when needed and document them: your decisions and how you justify them are part of the evaluation.

---

## 2. The business question

Adi2's LAM leadership team reads the business as follows: **growth is coming from online, while physical stores are losing relevance.** They are considering shifting investment from stores to ECOM.

Using **Q1 2026 (Jan–Mar) vs Q1 2025**, in EUR:

1. **Is the data consistent with leadership's reading?** Support your answer with net sales by channel and country.
2. **Which stores drive the Retail result, and what explains it?**

Then add **2–3 insights of your own**, each as: *what you observe → what it means for the business → what you would do*.

You will present your answer to leadership (see section 3, step 4).

---

## 3. Your task

1. **Pipeline.** Extract every endpoint of the local API over HTTP (handling pagination completely), clean and standardize each source, and **persist the clean data as local files**, one per source, in the format of your choice. Do not use a database server or cloud service. It should run end to end from a single command or a notebook run top to bottom.
2. **Final table.** Join and transform the clean sources into `fact_sellout_performance` (contract in section 6), saved as **Parquet**.
3. **Answer.** Answer the business question using **only** your final table.
4. **Present.** Prepare a short deliverable for **leadership**: the answer to the business question and your insights, with **at least one chart**. The format is your choice (one-pager, a few slides, a dashboard, charts with short text…). Your audience is not technical: lead with the message, not the code.

**Study the data before transforming it.** Look at what each row represents, how the business rules above show up in each source and how records relate to each other and to the master tables. Real-world data is rarely as tidy as you would like.

---

## 4. Agenda

| Time | What happens |
|---|---|
| 0:00 – 2:00 | **Solve the case:** read this document, start the API, build the pipeline and the final table, answer the question and prepare your leadership deliverable. |
| 2:00 – 2:10 | **Business presentation (10 min):** present your deliverable as you would to leadership. |
| 2:10 – 2:20 | **Technical walkthrough (10 min):** walk us through your notebook or code, your key decisions and validations, and answer our questions. |

Manage your own time; as a guide, leave about 15 minutes for the leadership deliverable. **A correct, well-validated table with partial answers is worth more than complete answers on top of a wrong table.**

---

## 5. API

```bash
cd api
pip install -r requirements.txt
python api_server.py
```

- Base URL: `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.
- `GET /health` returns the number of records per endpoint.
- All data must be retrieved through the API, not by reading the JSON files directly.

| Endpoint | Description | Filters |
|---|---|---|
| `GET /retail/sales` | Own retail stores: point-of-sale transaction lines | `country` |
| `GET /ecom/sales` | ECOM: online order lines | `country` |
| `GET /stores` | Own store master | `country` |
| `GET /articles` | Article master | — |
| `GET /fx_rates` | Company fixed exchange rates to EUR | — |

All list endpoints accept `limit` (default 500, **max 2000**) and `skip`, and return:

```json
{ "total": 4456, "skip": 0, "limit": 2000, "count": 2000, "data": [ { ... } ] }
```

Use `total` to keep requesting pages until all records are retrieved.

```python
import requests
r = requests.get("http://localhost:8000/retail/sales", params={"limit": 2000, "skip": 0}).json()
print(r["total"], r["data"][0])
```

### Data dictionary

Amounts are in **local currency, excluding VAT**.

**`/retail/sales`** — one row per transaction line

| Column | Type | Description |
|---|---|---|
| transaction_number | str | Transaction (ticket) ID |
| line_number | int | Line within the transaction |
| transaction_type | str | `SALE` / `RETURN` |
| reversal_indicator | str | `X` if the line reverses (voids) a previous transaction; empty otherwise |
| original_tran_number | str | For returns and reversals: the original transaction |
| calendar_date | str | Accounting date |
| country | str | `CO`, `MX`, `AR` |
| store_spot | str | Store code (6 digits) |
| group_article | str | Article code |
| size_page | str | Size |
| sold_qty | int | Units sold |
| return_qty | int | Units returned |
| return_value | float | Returned value (positive) |
| net_qty | int | Net units of the line |
| net_sales | float | Net sales of the line |
| currency | str | Currency |

**`/ecom/sales`** — one row per online order line. Same measures as Retail (`transaction_type`, `reversal_indicator`, `original_tran_number`, `calendar_date`, `country`, `group_article`, `size_page`, `sold_qty`, `return_qty`, `return_value`, `net_qty`, `net_sales`, `currency`), plus:

| Column | Type | Description |
|---|---|---|
| ecom_reference_number | str | Online order ID |
| sor_itm | int | Order line |
| consumer_order_date | str | Date the consumer placed the order |
| order_origin | str | `WEB` / `APP` |
| fulfillment_channel | str | `DC` (distribution center) / `STORE` (own store) |
| store_spot | str | Store that shipped the order |

**`/stores`**: `store_spot`, `store_name`, `country`, `city`, `store_format` (`BRAND CENTER` / `STORE` / `OUTLET`).

**`/articles`**: `group_article`, `article_name`, `product_division` (`FOOTWEAR` / `APPAREL` / `ACCESSORIES`), `key_category`.

**`/fx_rates`**: `country`, `currency`, `units_per_eur` (local currency units per 1 EUR, fixed company rate).

---

## 6. Final table: `fact_sellout_performance`

**Grain:** one row per `month` × `country` × `channel` × `store_spot` × `group_article` × `fulfilled_by_store_flag`.

| Column | Description |
|---|---|
| month | `YYYY-MM` |
| country | `CO`, `MX`, `AR` |
| channel | `RETAIL` / `ECOM`: the channel the sale is reported in, according to the business rules in section 1 |
| store_spot / store_name | Own store the sale is attributed to; empty when no store is involved |
| group_article | Article code |
| product_division / key_category | From the article master |
| fulfilled_by_store_flag | `True` for online orders shipped by an own store |
| gross_qty, return_qty, net_qty | Units: net = gross − returns |
| gross_sales_eur, return_sales_eur, net_sales_eur | EUR at the company's fixed rate: net = gross − returns |

You may add columns, not remove them.

**Mandatory validations** (visible in your code or notebook output):

- Row counts and sales totals **before and after every join**: no rows lost or duplicated unintentionally.
- A **reconciliation** by channel of net sales (EUR) and net units: clean source totals → each record you excluded or reclassified (and why) → totals in `fact_sellout_performance`. Every difference must be explained.

---

## 7. Deliverables (end of hands-on time)

Share a folder or `.zip` with:

| Item | Description |
|---|---|
| Code | Pipeline + transformation (scripts and/or notebook) |
| `data/clean/` | Clean data per source (local files) |
| `fact_sellout_performance.parquet` | Final table |
| Leadership deliverable | Your answer and insights for leadership, in the format of your choice, with at least one chart (file, slides or an exported notebook section) |
| `NOTES.md` | How to run it · key decisions and assumptions, with their impact quantified when possible (rows, EUR, %) · data issues you found · one or two lines on how you used AI and how you verified its output |

---

## 8. What we evaluate

- **Data engineering:** complete extraction, correct types, robust cleaning, reproducible pipeline.
- **Data understanding:** your transformations reflect how the business operates, not only the schema.
- **Correctness and verification:** you can prove your table is right (counts, checks, reconciliation).
- **Business judgment:** clear, data-backed answers and actionable insights.
- **Communication:** a clear, well-structured message for a non-technical audience, supported by the right chart; and a clear technical walkthrough of your own work.
- **Critical use of AI:** AI tools are allowed and expected. We evaluate that you understand, validate and can defend everything you deliver.

---

## 9. FAQ

**Can I use AI tools (Copilot, ChatGPT, etc.)?** Yes. Be ready to explain and modify any part of your code in the conversation.

**Can I use libraries other than pandas (polars, duckdb, pyarrow…)?** Yes, any Python library that runs locally.

**Does the leadership deliverable need to look polished?** No. It needs a clear message, correct numbers and at least one chart that supports it. A simple one-pager or a few well-chosen charts with short text are enough.

**Can I ask questions during the session?** Yes. The interviewer acts as a business stakeholder. If something is ambiguous, you may also make an assumption and document it.

**What if a value looks wrong or a record seems duplicated?** Decide how to treat it, document the decision and quantify its impact. Do not silently drop data.

**What if I run out of time?** Prioritize a correct, validated table. Note in `NOTES.md` what you would do next. Still present what you have: a partial answer, clearly framed, is better than no presentation.
