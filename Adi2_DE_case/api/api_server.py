"""
Adi2 LAM — Local Data API

Usage:
    pip install -r requirements.txt
    python api_server.py            # serves ./data/extract
    # → http://localhost:8000      interactive docs: http://localhost:8000/docs
"""
import argparse
import json
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query

BASE = Path(__file__).parent / "data"
MAX_LIMIT = 2000


DATA_DIR = BASE / "extract"


def load(name: str) -> list:
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


RETAIL = load("retail_sales")
ECOM = load("ecom_sales")
STORES = load("stores")
ARTICLES = load("articles")
FX_RATES = load("fx_rates")

app = FastAPI(
    title="Adi2 LAM Data API",
    description="Sales data for Adi2 Latin America: own retail stores, ECOM and master data.",
    version="1.0.0",
)


def page(items: list, skip: int, limit: int) -> dict:
    sliced = items[skip: skip + limit]
    return {"total": len(items), "skip": skip, "limit": limit, "count": len(sliced), "data": sliced}


def norm(v):
    return str(v).strip().upper() if v is not None else None


def flt(items: list, **filters) -> list:
    active = {k: norm(v) for k, v in filters.items() if v is not None}
    if not active:
        return items
    return [r for r in items if all(norm(r.get(k)) == v for k, v in active.items())]


LimitQ = Query(default=500, ge=1, le=MAX_LIMIT, description=f"Page size (max {MAX_LIMIT})")
SkipQ = Query(default=0, ge=0, description="Number of records to skip")


@app.get("/health", tags=["utils"])
def health():
    return {
        "status": "ok",
        "records": {
            "retail_sales": len(RETAIL), "ecom_sales": len(ECOM),
            "stores": len(STORES), "articles": len(ARTICLES), "fx_rates": len(FX_RATES),
        },
    }


@app.get("/retail/sales", tags=["sales"], summary="Own retail stores: point-of-sale transaction lines")
def retail_sales(limit: int = LimitQ, skip: int = SkipQ, country: Optional[str] = None):
    return page(flt(RETAIL, country=country), skip, limit)


@app.get("/ecom/sales", tags=["sales"], summary="ECOM: online order lines")
def ecom_sales(limit: int = LimitQ, skip: int = SkipQ, country: Optional[str] = None):
    return page(flt(ECOM, country=country), skip, limit)


@app.get("/stores", tags=["master data"], summary="Own store master")
def stores(limit: int = LimitQ, skip: int = SkipQ, country: Optional[str] = None):
    return page(flt(STORES, country=country), skip, limit)


@app.get("/articles", tags=["master data"], summary="Article master")
def articles(limit: int = LimitQ, skip: int = SkipQ):
    return page(ARTICLES, skip, limit)


@app.get("/fx_rates", tags=["master data"], summary="Company fixed exchange rates to EUR")
def fx_rates(limit: int = LimitQ, skip: int = SkipQ):
    return page(FX_RATES, skip, limit)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    print(f"Serving data from {DATA_DIR}")
    uvicorn.run(app, host="127.0.0.1", port=args.port)
