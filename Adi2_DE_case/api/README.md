# Adi2 LAM — Local Data API

## Setup

```bash
pip install -r requirements.txt
python api_server.py            # http://localhost:8000
```

Interactive documentation: http://localhost:8000/docs

## Endpoints

| Endpoint | Description | Filters |
|---|---|---|
| `GET /health` | Status and record counts | — |
| `GET /retail/sales` | Own retail stores, POS transaction lines | `country` |
| `GET /ecom/sales` | ECOM order lines | `country` |
| `GET /stores` | Own store master | `country` |
| `GET /articles` | Article master | — |
| `GET /fx_rates` | Company fixed exchange rates to EUR | — |

All list endpoints accept `limit` (default 500, max 2000) and `skip`.
Filters are exact matches on the code (case-insensitive, surrounding spaces ignored).

## Response structure

```json
{ "total": 4456, "skip": 0, "limit": 500, "count": 500, "data": [ ... ] }
```

Use `total` to paginate until all records are retrieved.

## Quick start

```python
import requests
r = requests.get("http://localhost:8000/retail/sales", params={"limit": 2000, "skip": 0}).json()
print(r["total"], r["data"][0])
```
