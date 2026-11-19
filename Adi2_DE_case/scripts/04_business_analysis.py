"""Adi2 | Business analysis and offline HTML leadership presentation.

ONLY reads: data/analytics/fact_sellout_performance.parquet
Run: python scripts/04_business_analysis.py
Open: outputs/business/leadership_presentation.html
"""

from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FACT = ROOT / "data" / "analytics" / "fact_sellout_performance.parquet"
OUTPUT = ROOT / "outputs" / "business"

PERIOD_MONTHS = [
    f"{year}-{month:02d}"
    for year in (2025, 2026)
    for month in (1, 2, 3)
]

COUNTRY_NAMES = {"CO": "Colombia", "MX": "México", "AR": "Argentina"}
STORE_KEYS = ["country", "store_spot", "store_name"]


def compare_q1(df, dimensions):
    """Suma ventas netas, separa los Q1 y calcula variación interanual."""
    summary = (
        df.groupby(dimensions + ["year"], dropna=False)["net_sales_eur"]
        .sum()
        .unstack("year", fill_value=0)
        .reindex(columns=[2025, 2026], fill_value=0)
        .reset_index()
        .rename(columns={2025: "q1_2025_eur", 2026: "q1_2026_eur"})
    )
    summary["change_eur"] = summary["q1_2026_eur"] - summary["q1_2025_eur"]
    summary["growth_pct"] = np.where(
        summary["q1_2025_eur"].ne(0),
        summary["change_eur"] / summary["q1_2025_eur"] * 100,
        np.nan,
    )
    return summary


def euro(value, digits=2, signed=False):
    if pd.isna(value):
        return "—"
    prefix = "+" if signed and value > 0 else ("−" if value < 0 else "")
    number = f"{abs(float(value)):,.{digits}f}"
    number = number.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{prefix}€{number}"


def percent(value, signed=False):
    if pd.isna(value):
        return "n.d."
    prefix = "+" if signed and value > 0 else ("−" if value < 0 else "")
    return f"{prefix}{abs(float(value)):.2f}".replace(".", ",") + "%"


def points(value, signed=False):
    """Cambio de participación en puntos porcentuales (no %)."""
    if pd.isna(value):
        return "n.d."
    prefix = "+" if signed and value > 0 else ("−" if value < 0 else "")
    return f"{prefix}{abs(float(value)):.2f}".replace(".", ",") + " pp"


def safe(value):
    return escape(str(value), quote=True)


def value_for(df, column, value):
    matches = df.loc[df[column].eq(value)]
    if len(matches) != 1:
        raise ValueError(f"Expected one {column}={value}; found {len(matches)}")
    return matches.iloc[0]


def close(a, b, label):
    if not np.isclose(float(a), float(b), atol=0.01, rtol=0):
        raise ValueError(f"Reconciliation failed: {label}: {a} vs {b}")


def card(label, number, explanation, tone=""):
    return (
        f'<article class="metric {tone}">'
        f'<div class="metric-label">{safe(label)}</div>'
        f'<div class="metric-value">{number}</div>'
        f'<div class="metric-sub">{safe(explanation)}</div>'
        f'</article>'
    )


def paired_bars(row, max_value):
    channel = str(row["channel"])
    color = "retail" if channel == "RETAIL" else "ecom"
    lines = []
    for year in (2025, 2026):
        value = float(row[f"q1_{year}_eur"])
        width = max(0, 100 * value / max_value)
        lines.append(
            f'<div class="barline"><span class="bar-year">Q1 {year}</span>'
            f'<div class="bar-track"><div class="bar-fill {color} y{year}" '
            f'style="width:{width:.3f}%"></div></div>'
            f'<strong class="bar-amount">{euro(value, 0)}</strong></div>'
        )
    return (
        f'<div class="pair-group"><div class="pair-title">{safe(channel)}'
        f'<span class="pair-growth">{percent(row["growth_pct"], signed=True)}</span></div>'
        + "".join(lines) + "</div>"
    )


def country_table(df):
    order = {"CO": 0, "MX": 1, "AR": 2}
    rows = sorted(df.to_dict("records"), key=lambda r: (order.get(r["country"], 9), r["channel"] != "RETAIL"))
    html = []
    for r in rows:
        change = float(r["change_eur"])
        cls = "positive" if change >= 0 else "negative"
        html.append(
            f'<tr><td><b>{safe(COUNTRY_NAMES.get(r["country"], r["country"]))}</b></td>'
            f'<td><span class="tag {str(r["channel"]).lower()}">{safe(r["channel"])}</span></td>'
            f'<td class="num">{euro(r["q1_2025_eur"])}</td>'
            f'<td class="num">{euro(r["q1_2026_eur"])}</td>'
            f'<td class="num {cls}">{euro(change, signed=True)}</td>'
            f'<td class="num {cls}">{percent(r["growth_pct"], signed=True)}</td></tr>'
        )
    return "".join(html)


def online_mix_bar(year, dc, store):
    """Online-origin sales split: distribution centers vs store fulfillment."""
    total = dc + store
    dc_share = 100 * dc / total if total else 0
    store_share = 100 * store / total if total else 0
    return (
        f'<div class="mix"><div class="mix-header"><b>Q1 {year}</b>'
        f'<span>Compras originadas online: {euro(total, 0)}</span></div>'
        f'<div class="mix-track">'
        f'<div class="mix-floor" style="width:{dc_share:.3f}%"></div>'
        f'<div class="mix-online" style="width:{store_share:.3f}%"></div>'
        f'</div><div class="mix-detail"><span>Centros de distribución: {euro(dc, 0)} ({percent(dc_share)})</span>'
        f'<span>Tiendas: {euro(store, 0)} ({percent(store_share)})</span></div></div>'
    )


def market_comparison_table(markets, total_growth):
    output = []
    for _, r in markets.sort_values('q1_2026_eur', ascending=False).iterrows():
        country = safe(COUNTRY_NAMES.get(r['country'], r['country']))
        contrib = 100 * float(r['change_eur']) / total_growth if total_growth else np.nan
        output.append(
            '<tr>'
            f'<td><b>{country}</b></td>'
            f'<td class="num">{euro(r["q1_2025_eur"], 0)}</td>'
            f'<td class="num">{euro(r["q1_2026_eur"], 0)}</td>'
            f'<td class="num positive">{euro(r["change_eur"], 0, True)}</td>'
            f'<td class="num">{percent(r["growth_pct"], True)}</td>'
            f'<td class="num">{percent(contrib)}</td>'
            '</tr>'
        )
    return ''.join(output)


def country_drivers_table(market_origin, market_products):
    """Three additive sources of growth plus product evidence (separate cut)."""
    rows = []
    for country in ('CO','MX','AR'):
        part = market_origin.loc[market_origin['country'].eq(country)]
        def amount(origin):
            match = part.loc[part['origin_type'].eq(origin)]
            return float(match['change_eur'].sum())
        floor = amount('Venta presencial')
        store = amount('Online despachado por tienda')
        dc = amount('Online desde centro de distribución')
        shoe = float(market_products.loc[
            market_products['country'].eq(country)
            & market_products['product_division'].eq('FOOTWEAR'), 'change_eur'
        ].sum())
        rows.append(
            '<tr>'
            f'<td><b>{safe(COUNTRY_NAMES[country])}</b></td>'
            f'<td class="num {"positive" if floor >= 0 else "negative"}">{euro(floor, 0, True)}</td>'
            f'<td class="num positive">{euro(dc, 0, True)}</td>'
            f'<td class="num positive">{euro(store, 0, True)}</td>'
            f'<td class="num"><b>{euro(floor + dc + store, 0, True)}</b></td>'
            f'<td class="num">{euro(shoe, 0, True)}</td>'
            '</tr>'
        )
    return ''.join(rows)


def division_table(divisions, total_change):
    rows = []
    for _, r in divisions.sort_values('change_eur', ascending=False).iterrows():
        change = float(r['change_eur'])
        contrib = 100 * change / total_change if total_change else np.nan
        rows.append(
            '<tr>'
            f'<td><b>{safe(r["product_division"])}</b></td>'
            f'<td class="num">{euro(r["q1_2025_eur"], 0)}</td>'
            f'<td class="num">{euro(r["q1_2026_eur"], 0)}</td>'
            f'<td class="num {"positive" if change >= 0 else "negative"}">{euro(change, 0, True)}</td>'
            f'<td class="num">{percent(r["growth_pct"], True)}</td>'
            f'<td class="num">{percent(contrib, True)}</td>'
            '</tr>'
        )
    return ''.join(rows)


def returns_table(returns):
    rows = []
    for ch in ('RETAIL','ECOM'):
        for year in (2025,2026):
            r = returns.loc[returns['channel'].eq(ch) & returns['year'].eq(year)]
            if len(r) != 1:
                raise ValueError(f'Missing returns KPI {ch} {year}')
            r=r.iloc[0]
            rows.append(
                '<tr>'
                f'<td><span class="tag {ch.lower()}">{ch}</span></td>'
                f'<td>Q1 {year}</td>'
                f'<td class="num">{euro(r["gross_sales_eur"], 0)}</td>'
                f'<td class="num">{euro(r["return_sales_eur"], 0)}</td>'
                f'<td class="num"><b>{percent(r["return_rate_pct"])}</b></td>'
                '</tr>'
            )
    return ''.join(rows)

def mix_bar(year, floor, ship):
    total = floor + ship
    floor_pct = 100 * floor / total if total else 0
    ship_pct = 100 - floor_pct if total else 0
    return (
        f'<div class="mix"><div class="mix-header"><b>Q1 {year}</b>'
        f'<span>Total Retail {euro(total)}</span></div>'
        f'<div class="mix-track">'
        f'<div class="mix-floor" style="width:{floor_pct:.3f}%"></div>'
        f'<div class="mix-online" style="width:{ship_pct:.3f}%"></div>'
        f'</div><div class="mix-detail"><span>Presencial: {euro(floor)} ({percent(floor_pct)})</span>'
        f'<span>Online desde tienda: {euro(ship)} ({percent(ship_pct)})</span></div></div>'
    )


def store_driver_rows(frame, max_abs):
    result = []
    for _, r in frame.iterrows():
        value = float(r["change_eur"])
        width = 100 * abs(value) / max_abs if max_abs else 0
        bg = "gain" if value >= 0 else "loss"
        left = (
            f'<div class="neg-bar" style="width:{width:.2f}%"></div>'
            if value < 0 else ""
        )
        right = (
            f'<div class="pos-bar" style="width:{width:.2f}%"></div>'
            if value >= 0 else ""
        )
        name = safe(r["store_name"])
        country = safe(r["country"])
        result.append(
            f'<div class="store-row"><div class="store-label"><b>{name}</b>'
            f'<span>{country}</span></div>'
            f'<div class="store-split"><div class="negative-side">{left}</div>'
            f'<div class="positive-side">{right}</div></div>'
            f'<strong class="store-value {bg}">{euro(value, 0, signed=True)}</strong>'
            f'<div class="store-explain">Piso {euro(r["floor_change_eur"], 0, signed=True)}'
            f' · Online {euro(r["ship_change_eur"], 0, signed=True)}</div></div>'
        )
    return "".join(result)


def store_detail_table(stores):
    rows = []
    for _, r in stores.iterrows():
        gain = "positive" if r["change_eur"] >= 0 else "negative"
        rows.append(
            "<tr>"
            f'<td>{safe(COUNTRY_NAMES.get(r["country"], r["country"]))}</td>'
            f'<td><b>{safe(r["store_name"])}</b></td>'
            f'<td class="num">{euro(r["q1_2025_eur"])}</td>'
            f'<td class="num">{euro(r["q1_2026_eur"])}</td>'
            f'<td class="num {gain}">{euro(r["change_eur"], signed=True)}</td>'
            f'<td class="num">{euro(r["floor_change_eur"], signed=True)}</td>'
            f'<td class="num">{euro(r["ship_change_eur"], signed=True)}</td>'
            "</tr>"
        )
    return "".join(rows)


def slide(index, kind, eyebrow, title, subtitle, body, footer):
    active = " active" if index == 1 else ""
    return f'''
<section class="slide {kind}{active}" id="s{index}">
  <div class="slide-top"><span class="brand">ADI<span>2</span> / LAM</span>
  <span class="section-label">{safe(eyebrow)} · Q1 2026 VS. Q1 2025</span></div>
  <header class="slide-heading"><h1>{title}</h1><p>{subtitle}</p></header>
  {body}
  <footer class="slide-bottom"><span>{safe(footer)}</span><span>{index:02d} / 10</span></footer>
</section>'''


def build_html(tables):
    ch = tables["channel"]
    countries = tables["countries"]
    totals = tables["total"].iloc[0]
    origin = tables["origin"]
    mix = tables["mix"]
    stores = tables["stores"]
    country_total = tables["country_total"]
    divisions = tables["divisions"]
    returns = tables["returns"]
    market_origin = tables["country_origin"]
    market_products = tables["country_divisions"]
    online_dispatch = tables["online_dispatch"]

    retail = value_for(ch, "channel", "RETAIL")
    ecom = value_for(ch, "channel", "ECOM")
    floor = value_for(mix, "fulfilled_by_store_flag", False)
    ship = value_for(mix, "fulfilled_by_store_flag", True)
    online = value_for(origin, "origin_type", "Compra online")
    physical = value_for(origin, "origin_type", "Compra presencial")
    store_dispatch = value_for(online_dispatch, "dispatch_type", "Despacho desde tienda")
    dc_dispatch = value_for(online_dispatch, "dispatch_type", "Centro de distribución")

    best = stores.iloc[0]
    worst = stores.iloc[-1]
    leader = country_total.sort_values("change_eur", ascending=False).iloc[0]
    division_leader = divisions.sort_values("change_eur", ascending=False).iloc[0]
    return_retail = returns.loc[returns["channel"].eq("RETAIL")].set_index("year")
    rate_2025 = float(return_retail.loc[2025, "return_rate_pct"])
    rate_2026 = float(return_retail.loc[2026, "return_rate_pct"])
    rate_pp = rate_2026 - rate_2025
    total_growth = float(totals["change_eur"])
    country_contrib = 100 * float(leader["change_eur"]) / total_growth if total_growth else np.nan
    division_contrib = 100 * float(division_leader["change_eur"]) / total_growth if total_growth else np.nan
    ship_2025_share = 100 * float(ship["q1_2025_eur"]) / float(retail["q1_2025_eur"])
    ship_2026_share = 100 * float(ship["q1_2026_eur"]) / float(retail["q1_2026_eur"])
    online_store_pct_2025 = (
        100 * float(store_dispatch["q1_2025_eur"]) / float(online["q1_2025_eur"])
    )
    online_store_pct_2026 = (
        100 * float(store_dispatch["q1_2026_eur"]) / float(online["q1_2026_eur"])
    )
    col = value_for(country_total, "country", "CO")
    mx = value_for(country_total, "country", "MX")
    ar = value_for(country_total, "country", "AR")
    col_foot = market_products.loc[
        market_products["country"].eq("CO")
        & market_products["product_division"].eq("FOOTWEAR")
    ]
    if len(col_foot) != 1:
        raise ValueError("Colombia FOOTWEAR missing")
    col_foot = col_foot.iloc[0]

    style = r'''
:root { --bg:#0C1016; --card:#171E28; --card2:#202A36; --ink:#F7FAFF;
  --muted:#ACB8C8; --line:#344152; --lime:#D7FF59; --blue:#7CA9FF;
  --teal:#64E6C4; --red:#FF8E8E; --shade:#111821; }
* { box-sizing: border-box; }
html { background:var(--bg); scroll-behavior:smooth; }
body { margin:0; background:var(--bg); color:var(--ink); font-family:Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }
.slide { display:none; margin:auto; min-height:100vh; max-width:1500px; padding:50px 5vw 76px; position:relative; }
.slide.active { display:block; }
.slide-top,.slide-bottom { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.slide-top { font-size:12px; letter-spacing:.17em; color:var(--muted); text-transform:uppercase; }
.brand { font-size:18px; font-weight:900; color:var(--ink); letter-spacing:-.035em; }
.brand span { color:var(--lime); }
.slide-heading { margin:28px 0 22px; }
.slide-heading h1 { margin:0 0 12px; font-size:clamp(28px,3.2vw,52px); letter-spacing:-.045em; line-height:1.08; font-weight:850; max-width:1180px; }
.slide-heading p { margin:0; font-size:clamp(14px,1.3vw,18px); line-height:1.45; color:var(--muted); max-width:1040px; }
.slide-bottom { border-top:1px solid var(--line); color:#8F9EB1; font-size:11px; letter-spacing:.04em; margin-top:26px; padding-top:16px; }
.hero { background:radial-gradient(circle at 95% 0%, #263F2C 0%, transparent 40%),var(--bg); }
.hero .slide-heading h1 { max-width:1100px; font-size:clamp(35px,4.3vw,65px); }
.lime { color:var(--lime); } .blue-text{color:var(--blue)} .negative{color:var(--red)} .positive{color:var(--teal)}
.metric-row { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:26px 0; }
.metric { border:1px solid var(--line); background:var(--card); border-radius:16px; padding:22px; min-width:0; }
.metric-label { text-transform:uppercase; color:var(--muted); font-size:11px; font-weight:750; letter-spacing:.09em; }
.metric-value { font-weight:850; font-size:clamp(24px,3.2vw,44px); letter-spacing:-.05em; margin:12px 0 6px; white-space:nowrap; }
.metric.good .metric-value { color:var(--teal); } .metric.warn .metric-value { color:var(--red); }
.metric-sub { color:var(--muted); font-size:12px; line-height:1.4; }
.statement { background:var(--lime); color:#142017; border-radius:15px; padding:20px 25px; font-size:clamp(16px,1.65vw,23px); line-height:1.35; letter-spacing:-.02em; font-weight:740; }

/* Portada: planteamiento de la decisión, sin anticipar resultados. */
.hyp-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; margin:23px 0 16px; }
.hyp { background:var(--card); border:1px solid var(--line); border-radius:17px; padding:23px 25px; min-height:148px; }
.hyp .hyp-id { display:inline-block; color:var(--lime); font-size:12px; letter-spacing:.14em; font-weight:850; margin-bottom:12px; }
.hyp h2 { margin:0 0 8px; font-size:clamp(19px,1.65vw,25px); line-height:1.15; letter-spacing:-.025em; }
.hyp p { color:var(--muted); line-height:1.45; font-size:13px; margin:0; }
.open-decision { background:linear-gradient(95deg,#D7FF59,#C4EF64); color:#172119; padding:17px 24px; border-radius:14px; font-size:clamp(16px,1.45vw,21px); font-weight:780; line-height:1.35; }
.open-decision strong { font-size:11px; text-transform:uppercase; letter-spacing:.12em; display:inline-block; margin-right:12px; opacity:.78; }
.evidence-track { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-top:17px; }
.evidence-item { background:#14202A; border:1px solid #293B48; border-radius:12px; padding:14px 16px; font-size:13px; line-height:1.35; color:#DEEBF2; }
.evidence-item b { color:var(--lime); font-size:13px; margin-right:9px; }

.two-col { display:grid; grid-template-columns: 1fr 1fr; gap:20px; }
.panel { background:var(--card); border:1px solid var(--line); padding:20px 24px; border-radius:16px; }
.panel-title { margin:0 0 18px; font-size:15px; font-weight:750; letter-spacing:-.01em; }
.pair-group { margin-bottom:22px; } .pair-title { display:flex; align-items:center; justify-content:space-between; font-weight:800; margin-bottom:10px; }
.pair-growth { color:var(--teal); font-size:15px; }
.barline { display:grid; grid-template-columns:65px 1fr 106px; gap:12px; align-items:center; margin:9px 0; font-size:13px; }
.bar-year { color:var(--muted); white-space:nowrap; } .bar-track { background:#303A48; height:17px; overflow:hidden; border-radius:5px; }
.bar-fill { height:100%; border-radius:5px; } .bar-fill.retail { background:var(--lime); } .bar-fill.ecom { background:var(--blue); }
.bar-fill.y2025 { opacity:.42; } .bar-amount { white-space:nowrap; text-align:right; font-variant-numeric:tabular-nums; }
.legend { color:var(--muted); font-size:12px; }
.table-scroll { overflow:auto; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th,td { border-bottom:1px solid #344152; padding:12px 10px; text-align:left; }
th { color:var(--muted); font-size:11px; letter-spacing:.045em; text-transform:uppercase; font-weight:750; }
.num { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
.tag { font-size:10px; font-weight:850; letter-spacing:.08em; border-radius:5px; padding:4px 7px; background:#2A3749; color:#D3E1FF; }
.tag.retail { background:#3D4422; color:#E3FF93; } .tag.ecom { background:#253860; color:#ACCBFF; }
.callout { margin-top:14px; padding:13px 17px; background:#1E2B31; border-left:3px solid var(--lime); border-radius:4px; line-height:1.5; font-size:13px; }
.mix { margin-bottom:18px; } .mix-header,.mix-detail { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.mix-header { font-size:15px; margin-bottom:8px; } .mix-header span { color:var(--muted); font-size:12px; }
.mix-track { height:34px; border-radius:8px; display:flex; overflow:hidden; background:#303A48; }
.mix-floor { background:var(--lime); } .mix-online { background:var(--blue); min-width:1px; }
.mix-detail { margin-top:8px; font-size:11px; color:var(--muted); }
.split-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:13px; margin:22px 0; }
.big-figure { background:var(--card2); padding:18px; border-radius:12px; }
.big-figure .value { font-size:clamp(21px,2.3vw,34px); font-weight:850; white-space:nowrap; }
.big-figure small { display:block; color:var(--muted); margin-top:9px; font-size:12px; line-height:1.4; }
.store-columns { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
.store-row { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(90px,1fr) 100px; gap:9px; align-items:center; padding:8px 0; border-bottom:1px solid #2C3948; }
.store-label { font-size:11px; min-width:0; } .store-label b { display:block; overflow-wrap:anywhere; } .store-label span { display:inline-block; margin-top:3px; color:var(--muted); }
.store-split { display:flex; height:14px; } .negative-side,.positive-side { width:50%; display:flex; align-items:center; }
.negative-side { justify-content:flex-end; border-right:1px solid #8B96A5; } .positive-side { justify-content:flex-start; }
.neg-bar,.pos-bar { height:100%; } .neg-bar { background:var(--red); border-radius:3px 0 0 3px; }
.pos-bar { background:var(--teal); border-radius:0 3px 3px 0; }
.store-value { text-align:right; font-size:11px; white-space:nowrap; font-variant-numeric:tabular-nums; } .store-value.gain { color:var(--teal); }.store-value.loss { color:var(--red); }
.store-explain { grid-column:1 / -1; margin-top:-4px; color:var(--muted); font-size:10px; }
.insight-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
.insight { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:24px; }
.insight .number { color:var(--lime); font-weight:850; font-size:13px; letter-spacing:.1em; }
.insight h3 { font-size:23px; letter-spacing:-.03em; line-height:1.15; margin:18px 0; }
.insight p { font-size:13px; line-height:1.5; color:#D9E2EF; margin:13px 0; } .insight p b { color:var(--lime); }
.decision-grid { display:grid; grid-template-columns:1fr 1fr; gap:17px; }
.step { display:flex; gap:15px; padding:14px 0; border-bottom:1px solid var(--line); }
.step-n { font-size:24px; color:var(--lime); font-weight:850; width:38px; flex-shrink:0; }
.step p { margin:4px 0 0; color:var(--muted); font-size:13px; line-height:1.5; }
.footnote { padding:15px 18px; background:#1B2632; border-radius:10px; font-size:12px; line-height:1.5; color:#C2CFDC; }

/* Evidencia cuantitativa nueva. */
.mini-eyebrow { color:var(--lime); font-size:11px; font-weight:800; letter-spacing:.10em; text-transform:uppercase; }
.context-banner { margin-top:14px; background:#1F2935; border-left:3px solid var(--lime); border-radius:7px; padding:11px 15px; font-size:12px; line-height:1.4; color:#E4EAF3; }
.stat-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:14px 0; }
.stat-tile { background:var(--card2); padding:13px 17px; border:1px solid #374250; border-radius:12px; }
.stat-tile small { display:block; color:var(--muted); font-size:11px; line-height:1.35; }
.stat-tile strong { display:block; font-size:24px; font-weight:850; margin:7px 0 4px; letter-spacing:-.025em; }
.stats-2col { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.proof-list { padding:0; margin:10px 0 0; list-style:none; }
.proof-list li { border-bottom:1px solid var(--line); padding:10px 0; line-height:1.42; font-size:12px; }
.proof-list li:last-child {border-bottom:0}
.proof-list b { color:var(--lime); }
.questions-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.answer { border:1px solid var(--line); border-radius:16px; background:var(--card); padding:20px 23px; }
.answer h2 { margin:0 0 12px; font-size:20px; letter-spacing:-.022em; }
.answer .verdict { color:var(--lime); font-weight:800; font-size:16px; }
.answer p { color:#DBE4EE; font-size:13px; line-height:1.5; margin:10px 0; }
.answer .proof { margin-top:13px; background:#23313B; border-radius:8px; padding:12px 14px; font-size:12px; line-height:1.5; color:#E4ECF4; }
.answer .proof strong { color:var(--teal); }
.fineprint { font-size:11px; line-height:1.45; color:var(--muted); margin-top:10px; }
.slide.tight { padding-top:28px; }
.slide.tight .slide-heading { margin:17px 0 13px; }
.slide.tight .panel { padding:14px 18px; }
.slide.tight th,.slide.tight td { padding:8px 8px; font-size:12px; }
.slide.tight .mix { margin-bottom:12px; }
.slide.tight .split-grid { margin:12px 0; }
@media(max-width:900px) { .stats-2col,.questions-grid,.stat-grid { grid-template-columns:1fr; } }
@media print { .slide.tight { padding-top:19px; } .stat-tile strong { font-size:20px; } .answer { padding:14px; } .answer h2 { font-size:18px; } .answer p { font-size:11px; } }


/* 9. Planes de accion medibles para liderazgo. */
.strategy-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin-top:18px; }
.strategy-card { background:var(--card); border:1px solid var(--line); border-top:4px solid var(--lime); border-radius:15px; padding:20px 21px; min-width:0; display:flex; flex-direction:column; gap:9px; }
.strategy-card h2 { margin:4px 0 7px; font-size:21px; line-height:1.12; letter-spacing:-.025em; }
.strategy-card p { color:#D7E0EB; font-size:12px; line-height:1.42; margin:0 0 5px; }
.strategy-card .strategy-kicker { color:var(--lime); font-size:11px; letter-spacing:.09em; font-weight:850; }
.strategy-card .strategy-label { color:var(--lime); text-transform:uppercase; letter-spacing:.08em; font-size:10px; font-weight:850; margin-top:5px; }
.strategy-card .strategy-metric { padding:10px 12px; border-radius:9px; background:#222F3B; color:#E4EEF8; font-weight:700; font-size:12px; line-height:1.35; }
.strategy-conclusion { background:#202C34; border-left:3px solid var(--lime); border-radius:7px; padding:12px 16px; margin-top:14px; font-size:13px; line-height:1.38; }
@media (max-width:900px) { .strategy-grid { grid-template-columns:1fr; } }
@media print { .strategy-card { padding:12px; gap:6px; } .strategy-card h2 { font-size:17px; } .strategy-card p { font-size:10px; } .strategy-conclusion { padding:9px; font-size:11px; } }

.annex table { font-size:12px; } .annex td,.annex th { padding:10px 7px; }
.controls { position:fixed; right:22px; bottom:20px; display:flex; gap:8px; align-items:center; z-index:10; padding:7px 9px; border:1px solid #3B4C5C; background:#1C2631; border-radius:99px; box-shadow:0 10px 25px #0007; }
.controls button { border:0; border-radius:50px; background:#314252; color:white; padding:9px 14px; font-weight:750; cursor:pointer; }
.controls button:hover { background:var(--lime); color:#172018; }
#counter { color:var(--muted); font-size:12px; min-width:44px; text-align:center; }
/* La página de países necesita menos aire para mostrarse en pantalla completa. */
.slide.compact { padding-top:26px; padding-bottom:38px; }
.slide.compact .slide-heading { margin:17px 0 16px; }
.slide.compact .panel { padding:14px 20px; }
.slide.compact .pair-group { margin-bottom:12px; }
.slide.compact .barline { margin:6px 0; }
.slide.compact th,.slide.compact td { padding:8px 9px; }
@media (max-width:900px) { .hyp-grid,.evidence-track { grid-template-columns:1fr; } .slide { padding:28px 4vw 95px; } .metric-row,.insight-grid,.split-grid { grid-template-columns:1fr; } .two-col,.store-columns,.decision-grid { grid-template-columns:1fr; } .metric-value { font-size:28px; } .mix-detail { flex-direction:column; align-items:flex-start; } }
@media print {
 @page { size:landscape; margin:0; }
 html,body { background:var(--bg)!important; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
 .controls { display:none!important; }
 .slide,.slide.active { display:block!important; width:100%; max-width:none; min-height:100vh; height:100vh; padding:28px 44px 36px; page-break-after:always; break-after:page; overflow:hidden; }
 .slide-heading { margin:15px 0 12px; } .slide-heading h1 { font-size:34px; }
 .slide-heading p { font-size:13px; } .hyp-grid { margin:15px 0 10px; gap:12px; } .hyp { padding:13px 17px; min-height:0; } .hyp .hyp-id { margin-bottom:6px; } .hyp h2 { font-size:19px; margin-bottom:5px; } .hyp p { font-size:11px; } .open-decision { padding:13px 18px; font-size:16px; } .evidence-track { margin-top:10px; } .evidence-item { padding:10px; font-size:11px; } .metric-row { margin:14px 0; }
 .metric { padding:14px; } .metric-value { font-size:28px; } .panel { padding:14px; }
 .insight { padding:14px; } .insight h3 { font-size:19px; } .insight p { font-size:12px; }
 .store-row { padding:4px 0; } .slide-bottom { position:absolute; bottom:18px; left:44px; right:44px; margin:0; }
}
'''

    # 1. Presentar el problema y las hipótesis, NO la conclusión.
    body1 = (
        '<div class="hyp-grid">'
        '<article class="hyp"><span class="hyp-id">HIPÓTESIS 01</span>'
        '<h2>El crecimiento viene principalmente de las compras online.</h2>'
        '<p>¿Qué muestran las ventas netas y el crecimiento de Retail y ECOM por país?</p>'
        '</article>'
        '<article class="hyp"><span class="hyp-id">HIPÓTESIS 02</span>'
        '<h2>Las tiendas físicas están perdiendo relevancia.</h2>'
        '<p>¿Qué papel tienen las ventas presenciales y los pedidos online despachados desde tiendas?</p>'
        '</article></div>'
        '<div class="open-decision"><strong>Decisión a evaluar</strong>'
        '¿Conviene trasladar inversión de tiendas físicas hacia ECOM?</div>'
        '<div class="evidence-track">'
        '<div class="evidence-item"><b>01</b> Ventas y crecimiento por canal y país</div>'
        '<div class="evidence-item"><b>02</b> Contribución omnicanal y desempeño por tienda</div>'
        '<div class="evidence-item"><b>03</b> Insights, riesgos y recomendación de inversión</div>'
        '</div>'
    )
    s1 = slide(1, "hero", "Contexto / Pregunta de negocio",
        "¿De dónde viene el crecimiento?<br><span class='lime'>¿Qué papel cumplen las tiendas?</span>",
        "Adi2 considera reasignar inversión de tiendas físicas a ECOM. Contrastamos dos hipótesis con las ventas netas de Q1 2026 frente a Q1 2025, expresadas en EUR.",
        body1,
        "Fuente de análisis: fact_sellout_performance.parquet · Colombia, México y Argentina")

    # 2. Channels + country details
    chart = "".join(paired_bars(r, max(float(ch["q1_2025_eur"].max()), float(ch["q1_2026_eur"].max()))) for _, r in ch.sort_values("channel",ascending=False).iterrows())
    body2 = (
        '<div class="two-col"><div class="panel"><h2 class="panel-title">Ventas por canal reportado</h2>'
        + chart + '<p class="legend">Barras claras: 2026 · barras atenuadas: 2025</p></div>'
        '<div class="panel"><h2 class="panel-title">Diferencia de crecimiento</h2>'
        '<div class="big-figure"><div class="value positive">' + euro(ecom["change_eur"],0,True) + '</div>'
        '<small>Incremento de ECOM en el trimestre</small></div><br>'
        '<div class="big-figure"><div class="value positive">' + euro(retail["change_eur"],0,True) + '</div>'
        '<small>Incremento de Retail; no está disminuyendo en ventas atribuidas</small></div></div></div>'
        '<div class="panel" style="margin-top:16px"><h2 class="panel-title">Ventas netas por país y canal · EUR</h2>'
        '<div class="table-scroll"><table><thead><tr><th>País</th><th>Canal</th><th class="num">Q1 2025</th><th class="num">Q1 2026</th><th class="num">Cambio EUR</th><th class="num">Cambio %</th></tr></thead>'
        '<tbody>' + country_table(countries) + '</tbody></table></div></div>'
    )
    s2 = slide(2,"compact","Pregunta 1 / Canales y países","¿Cómo crecen Retail y ECOM?",
        f'ECOM {percent(ecom["growth_pct"],True)} vs. Retail {percent(retail["growth_pct"],True)}. La diferencia es consistente en Colombia, México y Argentina.',body2,
        "Canal reportado: pedidos online despachados por tiendas se atribuyen a RETAIL")

    # 3. Relación entre origen online y canal reportado.
    body3 = (
        '<div class="stats-2col">'
        '<div class="panel"><h2 class="panel-title">De las compras originadas online, ¿desde dónde se despachan?</h2>'
        + online_mix_bar(2025, float(dc_dispatch["q1_2025_eur"]), float(store_dispatch["q1_2025_eur"]))
        + online_mix_bar(2026, float(dc_dispatch["q1_2026_eur"]), float(store_dispatch["q1_2026_eur"]))
        + '</div>'
        '<div class="panel"><h2 class="panel-title">¿De qué se compone Retail?</h2>'
        + mix_bar(2025, float(floor["q1_2025_eur"]), float(ship["q1_2025_eur"]))
        + mix_bar(2026, float(floor["q1_2026_eur"]), float(ship["q1_2026_eur"]))
        + '</div></div>'
        '<div class="stat-grid">'
        '<div class="stat-tile"><small>Participación de tienda en compras online · 2026</small>'
        '<strong class="lime">' + percent(online_store_pct_2026) + '</strong>'
        '<small>Frente al ' + percent(online_store_pct_2025) + ' de Q1 2025</small></div>'
        '<div class="stat-tile"><small>Cambio de ventas presenciales</small>'
        '<strong class="negative">' + euro(floor["change_eur"], 0, True) + '</strong>'
        '<small>' + percent(floor["growth_pct"], True) + ' frente a Q1 2025</small></div>'
        '<div class="stat-tile"><small>Cambio de ventas online despachadas por tienda</small>'
        '<strong class="positive">' + euro(ship["change_eur"], 0, True) + '</strong>'
        '<small>Crece el papel del fulfillment propio</small></div>'
        '</div><div class="context-banner"><b>Importante:</b> la proporción se mide sobre '
        '<b>ventas netas en EUR</b>, no sobre número de pedidos. '
        'Online = ECOM (centro de distribución) + Retail (despacho desde tienda). '
        'El canal de reporte y el origen de la compra no son lo mismo.</div>'
    )
    s3 = slide(3, "tight", "Pregunta 1 / Origen vs. atribución",
        "¿Qué parte del comercio online depende de las tiendas?",
        "Separamos la compra originada online según dónde se despacha, y también el resultado Retail según su origen operativo.",
        body3,
        "Fuente: tabla final · porcentajes sobre ventas netas EUR · no se cuentan pedidos individuales")

    # 4. Store drivers
    max_abs = float(stores["change_eur"].abs().max())
    body4 = (
        '<div class="store-columns"><div class="panel"><h2 class="panel-title">Mayor contribución al crecimiento</h2>'
        + store_driver_rows(stores.head(6), max_abs) + '</div>'
        + '<div class="panel"><h2 class="panel-title">Crecimiento limitado o caída</h2>'
        + store_driver_rows(stores.tail(6), max_abs) + '</div></div>'
        + '<div class="callout"><b>Ejemplo:</b> ' + safe(best["store_name"]) + ' (' + safe(best["country"]) + ') aporta '
        + euro(best["change_eur"],0,True) + ': piso ' + euro(best["floor_change_eur"],0,True)
        + ' y despacho online ' + euro(best["ship_change_eur"],0,True) + '. En contraste, '
        + safe(worst["store_name"]) + ' registra ' + euro(worst["change_eur"],0,True) + '.</div>'
    )
    s4 = slide(4,"","Pregunta 2 / Desempeño por tienda","¿Qué tiendas explican el resultado de Retail?",
        "Variación absoluta en EUR; cada tienda se descompone en venta presencial y online despachado desde su inventario.",body4,
        "Las 12 tiendas están incluidas · mayor detalle por período en el anexo")

    # 5. Explicación Colombia vs. México y Argentina, evidencia.
    body5 = (
        '<div class="panel"><h2 class="panel-title">Tamaño, ritmo y contribución · ventas netas EUR</h2>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>Mercado</th><th class="num">Q1 2025</th><th class="num">Q1 2026</th>'
        '<th class="num">Δ EUR</th><th class="num">Δ %</th>'
        '<th class="num">Aporte al Δ LAM</th></tr></thead><tbody>'
        + market_comparison_table(country_total, total_growth)
        + '</tbody></table></div></div>'
        '<div class="panel" style="margin-top:13px"><h2 class="panel-title">Qué componentes explican el cambio de cada país · Δ EUR</h2>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>País</th><th class="num">Presencial</th><th class="num">Online desde DC</th>'
        '<th class="num">Online desde tienda</th><th class="num">Δ neto país</th>'
        '<th class="num">Δ Footwear*</th></tr></thead><tbody>'
        + country_drivers_table(market_origin, market_products)
        + '</tbody></table></div>'
        '<p class="fineprint">* Footwear es otra descomposición (por producto): no se suma a los tres componentes por origen.</p>'
        '</div>'
        '<div class="context-banner"><b>Lectura:</b> México vende más en términos absolutos ('
        + euro(mx["q1_2026_eur"], 0) + '), pero Colombia registra el mayor crecimiento ('
        + percent(col["growth_pct"], True) + '). En Colombia, Footwear aporta '
        + euro(col_foot["change_eur"], 0, True)
        + ' al incremento, mientras el crecimiento de pedidos online supera la caída presencial. '
        'La tabla demuestra las contribuciones, no la causa comercial última.</div>'
    )
    s5 = slide(5, "tight", "Análisis / Mercados",
        "Colombia acelera; México conserva el mayor volumen.",
        "Para explicar por qué difieren los países distinguimos tamaño, crecimiento y componentes de la variación.",
        body5,
        "Fuente: tabla final · Δ = Q1 2026 menos Q1 2025 · no inferir causalidad de marketing o costos")

    # 6. Evidencia visible antes de contar insights sobre producto y devoluciones.
    body6 = (
        '<div class="panel"><h2 class="panel-title">Divisiones de producto · ventas netas EUR</h2>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>División</th><th class="num">Q1 2025</th><th class="num">Q1 2026</th>'
        '<th class="num">Δ EUR</th><th class="num">Δ %</th>'
        '<th class="num">Aporte al crecimiento LAM</th></tr></thead><tbody>'
        + division_table(divisions, total_growth)
        + '</tbody></table></div></div>'
        '<div class="panel" style="margin-top:14px"><h2 class="panel-title">Devoluciones por canal · importe devuelto / venta bruta</h2>'
        '<div class="table-scroll"><table><thead><tr>'
        '<th>Canal</th><th>Periodo</th><th class="num">Venta bruta</th>'
        '<th class="num">Devuelto EUR</th><th class="num">Ratio de devolución</th>'
        '</tr></thead><tbody>'
        + returns_table(returns)
        + '</tbody></table></div>'
        '<p class="fineprint">El ratio compara importes monetarios y no equivale al porcentaje de productos devueltos.</p>'
        '</div>'
        '<div class="context-banner"><b>Dos señales:</b> Footwear aporta '
        + euro(division_leader["change_eur"], 0, True) + ' (' + percent(division_contrib)
        + ' del crecimiento regional). La tasa monetaria de devolución de Retail pasa de '
        + percent(rate_2025) + ' a ' + percent(rate_2026)
        + ' (' + points(rate_pp, True) + '). No conocemos todavía las causas de estas devoluciones.</div>'
    )
    s6 = slide(6, "tight", "Evidencia / Portafolio y devoluciones",
        "El portafolio impulsa ventas; las devoluciones presionan el neto.",
        "Las siguientes cifras respaldan los insights: crecimiento por división y devolución monetaria por canal.",
        body6,
        "Fuente: tabla final · ventas netas, brutas y devoluciones convertidas a EUR")

    # 7. Insights only after numerical evidence.
    direction = "aumenta" if rate_pp > 0 else "disminuye"
    return_action = (
        "auditar motivos de devolución por tienda, artículo y tipo de despacho antes de escalar."
        if rate_pp > 0 else
        "mantener el control de devoluciones y confirmar la tendencia por tienda y artículo."
    )
    insight_cards = (
        '<div class="insight-grid">'
        '<article class="insight"><div class="number">INSIGHT 01 · MERCADO</div>'
        '<h3>' + safe(COUNTRY_NAMES.get(leader["country"], leader["country"])) + ' aporta más al crecimiento</h3>'
        '<p><b>Observación:</b> ' + euro(leader["change_eur"], 0, True) + ' ('
        + percent(country_contrib) + ' del crecimiento neto LAM).</p>'
        '<p><b>Significado:</b> el mercado tiene un crecimiento elevado, no el mayor volumen: México sigue liderando las ventas.</p>'
        '<p><b>Acción:</b> analizar los artículos Footwear y la operación online de Colombia; probar iniciativas y medir margen antes de expandir.</p></article>'
        '<article class="insight"><div class="number">INSIGHT 02 · PORTAFOLIO</div>'
        '<h3>' + safe(division_leader["product_division"]) + ' lidera el incremento</h3>'
        '<p><b>Observación:</b> ' + euro(division_leader["change_eur"], 0, True)
        + ' (' + percent(division_contrib) + ' del aumento LAM).</p>'
        '<p><b>Significado:</b> una división concentra gran parte del crecimiento neto.</p>'
        '<p><b>Acción:</b> priorizar revisión de disponibilidad, surtido y margen de sus referencias más relevantes.</p></article>'
        '<article class="insight"><div class="number">INSIGHT 03 · DEVOLUCIONES</div>'
        '<h3>Devolución monetaria Retail ' + direction + '</h3>'
        '<p><b>Observación:</b> ' + percent(rate_2025) + ' → ' + percent(rate_2026)
        + ', un cambio de ' + points(rate_pp, True) + '.</p>'
        '<p><b>Significado:</b> una mayor porción de ventas brutas se descuenta antes de llegar al neto.</p>'
        '<p><b>Acción:</b> ' + return_action + '</p></article></div>'
        '<div class="context-banner"><b>Los tres insights parten de la evidencia de las pantallas anteriores:</b> '
        'no son afirmaciones basadas únicamente en la narrativa.</div>'
    )
    s7 = slide(7, "", "Tres insights / Observación · significado · acción",
        "Dónde acelerar, qué potenciar y qué controlar.",
        "Cada acción se basa en un cambio cuantificado y distingue hechos de hipótesis.",
        insight_cards,
        "Los resultados de mercado, división y devolución se muestran en las pantallas 5 y 6")

    # 8. ANSWERS TO THE TWO OFFICIAL BUSINESS QUESTIONS – penultimate slide.
    best_three = stores.head(3)
    worst_two = stores.tail(2).sort_values('change_eur')
    ranking_gain = '; '.join(
        f'{safe(r["store_name"])} ({euro(r["change_eur"], 0, True)})'
        for _, r in best_three.iterrows()
    )
    ranking_loss = '; '.join(
        f'{safe(r["store_name"])} ({euro(r["change_eur"], 0, True)})'
        for _, r in worst_two.iterrows()
    )
    body8 = (
        '<div class="questions-grid">'
        '<article class="answer"><div class="mini-eyebrow">PREGUNTA OFICIAL 01</div>'
        '<h2>¿Los datos respaldan la lectura de liderazgo?</h2>'
        '<div class="verdict">Parcialmente.</div>'
        '<p>ECOM reportado crece ' + percent(ecom["growth_pct"], True)
        + ' y Retail también crece ' + percent(retail["growth_pct"], True)
        + '. La venta presencial cae ' + percent(floor["growth_pct"], True)
        + ', pero la red de tiendas despacha una parte creciente de las compras online.</p>'
        '<div class="proof"><strong>Evidencia en EUR:</strong> ECOM '
        + euro(ecom["change_eur"], 0, True) + ' · Retail '
        + euro(retail["change_eur"], 0, True) + ' · Presencial '
        + euro(floor["change_eur"], 0, True) + '.<br>'
        'La participación de tiendas en compras originadas online pasa de '
        + percent(online_store_pct_2025) + ' a ' + percent(online_store_pct_2026)
        + '.</div></article>'
        '<article class="answer"><div class="mini-eyebrow">PREGUNTA OFICIAL 02</div>'
        '<h2>¿Qué tiendas impulsan Retail y qué lo explica?</h2>'
        '<div class="verdict">El aporte se concentra en tiendas con capacidad omnicanal.</div>'
        '<p>Lideran: ' + ranking_gain
        + '. En el caso de ' + safe(best["store_name"]) + ', el cambio combina '
        + euro(best["floor_change_eur"], 0, True) + ' de venta presencial y '
        + euro(best["ship_change_eur"], 0, True) + ' de despacho online.</p>'
        '<div class="proof"><strong>Contrapesos:</strong> '
        + ranking_loss + '. Conviene estudiar cada establecimiento, no aplicar una decisión única a todos.</div>'
        '</article></div>'
        '<div class="context-banner"><b>Decisión:</b> no trasladar inversión de Retail a ECOM de forma generalizada. '
        'Evaluar productividad presencial, capacidad de despacho, márgenes, devoluciones y costos por tienda. '
        'Este análisis demuestra contribución a ventas, <b>no</b> rentabilidad.</div>'
    )
    s8 = slide(8, "tight", "Respuestas oficiales / Decisión de inversión",
        "¿Qué nos dicen los datos y qué debe decidir Adi2?",
        "Respuestas explícitas a las dos preguntas de liderazgo, respaldadas por los resultados de las seis pantallas de evidencia.",
        body8,
        "Fuente: fact_sellout_performance.parquet · Q1 2026 frente a Q1 2025 · EUR")

    # 9. Tres estrategias propuestas a partir de los hallazgos.
    # Todos los porcentajes utilizados se calculan a partir de la fact.
    body9 = (
        '<div class="strategy-grid">'
        '<article class="strategy-card">'
        '<div class="strategy-kicker">01 · OMNICANAL</div>'
        '<h2>Potenciar tiendas como puntos de fulfillment</h2>'
        '<div class="strategy-metric">' + percent(online_store_pct_2026)
        + ' de las compras online (EUR) ya se despacha desde tiendas.</div>'
        '<div class="strategy-label">Implementación</div>'
        '<p>Probar durante 60–90 días un modelo de despacho desde tiendas seleccionadas, con locales comparables como referencia. Revisar capacidad, inventario y costo por pedido.</p>'
        '<div class="strategy-label">Cómo medir el éxito</div>'
        '<p>Pedidos a tiempo, costo por pedido, ventas netas atribuidas y margen de contribución.</p>'
        '</article>'

        '<article class="strategy-card">'
        '<div class="strategy-kicker">02 · RECUPERACIÓN RETAIL</div>'
        '<h2>Recuperar venta presencial y reducir devoluciones</h2>'
        '<div class="strategy-metric">Presencial ' + percent(floor["growth_pct"], True)
        + ' · devoluciones Retail ' + percent(rate_2025) + ' → ' + percent(rate_2026) + '.</div>'
        '<div class="strategy-label">Implementación</div>'
        '<p>Priorizar tiendas con caídas; investigar cambios por artículo, talla y operación. Pilotar mejoras de surtido, disponibilidad y proceso de devoluciones.</p>'
        '<div class="strategy-label">Cómo medir el éxito</div>'
        '<p>Variación de venta presencial comparable, devoluciones / venta bruta y quiebres de inventario.</p>'
        '</article>'

        '<article class="strategy-card">'
        '<div class="strategy-kicker">03 · INVERSIÓN FOCALIZADA</div>'
        '<h2>Priorizar mercados y categorías con mayor potencial</h2>'
        '<div class="strategy-metric">' + safe(COUNTRY_NAMES.get(leader["country"], leader["country"]))
        + ' explica ' + percent(country_contrib) + ' del crecimiento; '
        + safe(division_leader["product_division"]) + ' aporta ' + percent(division_contrib) + '.</div>'
        '<div class="strategy-label">Implementación</div>'
        '<p>Ejecutar pruebas de surtido y acciones comerciales por país y categoría, comparando resultados con grupos de control antes de expandir.</p>'
        '<div class="strategy-label">Cómo medir el éxito</div>'
        '<p>Ventas incrementales frente al control, margen, rotación y disponibilidad de producto.</p>'
        '</article></div>'
        '<div class="strategy-conclusion"><b>Decisión propuesta:</b> aprobar pilotos medibles antes de mover presupuesto entre canales. '
        'Ventas y crecimiento no equivalen a rentabilidad; se necesitan costos, márgenes y capacidad operativa.</div>'
    )
    s9 = slide(9, "tight", "Plan de acción / Próximos 90 días",
        "Tres estrategias para actuar sobre los hallazgos.",
        "Iniciativas concretas, con criterios de medición antes de escalar inversión.",
        body9,
        "Propuestas para evaluar · no son resultados ya demostrados por las ventas")

    # 10. Annex: all 12 stores. It can be shown during Q&A.
    body10 = (
        '<div class="panel annex"><h2 class="panel-title">Las 12 tiendas · ventas netas EUR y descomposición del cambio</h2>'
        '<div class="table-scroll"><table><thead><tr><th>País</th><th>Tienda</th><th class="num">Q1 2025</th>'
        '<th class="num">Q1 2026</th><th class="num">Δ total</th><th class="num">Δ presencial</th>'
        '<th class="num">Δ online desde tienda</th></tr></thead><tbody>'
        + store_detail_table(stores) + '</tbody></table></div></div>'
    )
    s10 = slide(10, "", "Anexo / Validación",
        "Detalle de las 12 tiendas.",
        "Material de respaldo para preguntas del liderazgo; la suma de sus contribuciones coincide con el cambio total Retail.",
        body10,
        "Fact única · ventas netas EUR · Q1 2026 menos Q1 2025")

    js = r'''
const slides=[...document.querySelectorAll('.slide')];
let current=0;
function show(n) {
  current=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((s,i)=>s.classList.toggle('active',i===current));
  document.getElementById('counter').textContent=`${current+1} / ${slides.length}`;
  window.scrollTo(0,0);
}
document.getElementById('prev').onclick=()=>show(current-1);
document.getElementById('next').onclick=()=>show(current+1);
document.getElementById('print').onclick=()=>window.print();
document.addEventListener('keydown',e=>{
  if(['ArrowRight','PageDown',' '].includes(e.key)) {e.preventDefault();show(current+1);}
  if(['ArrowLeft','PageUp'].includes(e.key)) {e.preventDefault();show(current-1);}
  if(e.key==='Home') show(0);
  if(e.key==='End') show(slides.length-1);
});
show(0);
'''

    return (
        '<!doctype html>\n<html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Adi2 LAM | Q1 2026 vs Q1 2025</title><style>' + style
        + '</style></head><body><main id="deck">' + ''.join([s1,s2,s3,s4,s5,s6,s7,s8,s9,s10])
        + '</main><nav class="controls" aria-label="Navegación de la presentación">'
        '<button id="prev" title="Anterior">←</button><span id="counter">1 / 10</span>'
        '<button id="next" title="Siguiente">→</button>'
        '<button id="print" title="Imprimir o guardar PDF">⎙</button></nav>'
        '<script>' + js + '</script></body></html>'
    )


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    if not FACT.exists():
        raise FileNotFoundError(f"No encuentro {FACT}. Ejecuta 03_transform.py primero.")

    # UNICA LECTURA DE DATOS DE TODO ESTE SCRIPT
    fact = pd.read_parquet(FACT)

    required = {
        "month", "country", "channel", "store_spot", "store_name",
        "group_article", "fulfilled_by_store_flag", "net_sales_eur",
        "gross_sales_eur", "return_sales_eur", "product_division"
    }
    if missing := required.difference(fact.columns):
        raise ValueError(f"Faltan columnas en la fact: {sorted(missing)}")

    grain = ["month", "country", "channel", "store_spot", "group_article", "fulfilled_by_store_flag"]
    if fact.duplicated(grain).any():
        raise ValueError("La tabla fact no respeta su granularidad: hay claves duplicadas")

    actual_months = set(fact["month"].dropna())
    if missing_months := set(PERIOD_MONTHS).difference(actual_months):
        raise ValueError(f"Meses faltantes en la fact: {sorted(missing_months)}")

    q1 = fact.loc[fact["month"].isin(PERIOD_MONTHS)].copy()
    q1["year"] = q1["month"].str[:4].astype(int)
    if q1["fulfilled_by_store_flag"].isna().any():
        raise ValueError("Hay banderas de fulfillment nulas")
    q1["fulfilled_by_store_flag"] = q1["fulfilled_by_store_flag"].astype(bool)

    if not q1["channel"].isin(["RETAIL", "ECOM"]).all():
        raise ValueError("Canal de reporte desconocido")

    # 1. Canales y países - pregunta oficial 1
    by_channel = compare_q1(q1, ["channel"])
    by_country_channel = compare_q1(q1, ["country", "channel"])
    by_country = compare_q1(q1, ["country"])
    total = compare_q1(q1.assign(scope="LAM"), ["scope"])

    # 2. Tiendas, piso de venta y fulfillment - preguntas oficiales 1 y 2
    retail = q1.loc[q1["channel"].eq("RETAIL")].copy()
    if retail[STORE_KEYS].isna().any().any():
        raise ValueError("Las ventas Retail tienen tiendas sin identificar")
    by_mix = compare_q1(retail, ["fulfilled_by_store_flag"])
    stores = compare_q1(retail, STORE_KEYS)
    floor = compare_q1(retail.loc[~retail["fulfilled_by_store_flag"]], STORE_KEYS)
    ship = compare_q1(retail.loc[retail["fulfilled_by_store_flag"]], STORE_KEYS)

    for extra, prefix in ((floor, "floor"), (ship, "ship")):
        extra = extra[STORE_KEYS + ["q1_2025_eur", "q1_2026_eur", "change_eur"]]
        extra = extra.rename(columns={
            "q1_2025_eur": f"{prefix}_2025_eur",
            "q1_2026_eur": f"{prefix}_2026_eur",
            "change_eur": f"{prefix}_change_eur",
        })
        stores = stores.merge(extra, on=STORE_KEYS, how="left", validate="one_to_one")

    component_columns = [
        f"{component}_{measure}_eur"
        for component in ("floor", "ship")
        for measure in ("2025", "2026", "change")
    ]
    stores[component_columns] = stores[component_columns].fillna(0)
    stores = stores.sort_values("change_eur", ascending=False).reset_index(drop=True)

    # Descomponer origen de la compra con los campos disponibles en la fact:
    # ECOM (despacho DC) + Retail bandera True = compra originada online.
    is_online = q1["channel"].eq("ECOM") | q1["fulfilled_by_store_flag"]
    if (q1["channel"].eq("ECOM") & q1["fulfilled_by_store_flag"]).any():
        raise ValueError("ECOM no debería tener fulfilled_by_store_flag=True")
    by_origin = compare_q1(q1.assign(origin_type=np.where(is_online, "Compra online", "Compra presencial")), ["origin_type"])

    # 3. Insights adicionales (no duplican las preguntas oficiales)
    by_division = compare_q1(q1, ["product_division"])
    by_country_division = compare_q1(q1, ["country", "product_division"])

    # Three mutually exclusive categories of sales origin.
    q1["origin_type"] = np.select(
        [q1["channel"].eq("ECOM"), q1["fulfilled_by_store_flag"]],
        ["Online desde centro de distribución", "Online despachado por tienda"],
        default="Venta presencial"
    )
    by_country_origin = compare_q1(q1, ["country", "origin_type"])

    # Only online-origin sales: which operation fulfilled each sale?
    online_lines = q1.loc[q1["origin_type"].ne("Venta presencial")].copy()
    online_lines["dispatch_type"] = np.where(
        online_lines["fulfilled_by_store_flag"],
        "Despacho desde tienda", "Centro de distribución"
    )
    by_online_dispatch = compare_q1(online_lines, ["dispatch_type"])
    return_rate = q1.groupby(["year", "channel"], as_index=False).agg(
        gross_sales_eur=("gross_sales_eur", "sum"),
        return_sales_eur=("return_sales_eur", "sum"),
        net_sales_eur=("net_sales_eur", "sum"),
    )
    return_rate["return_rate_pct"] = np.where(
        return_rate["gross_sales_eur"].ne(0),
        return_rate["return_sales_eur"] / return_rate["gross_sales_eur"] * 100,
        np.nan,
    )

    # 4. Controles independientes basados exclusivamente en la fact
    for year in (2025, 2026):
        suffix = f"q1_{year}_eur"
        close(by_channel[suffix].sum(), total.iloc[0][suffix], f"canales {year}")
        close(by_country_channel[suffix].sum(), total.iloc[0][suffix], f"país-canal {year}")
        close(by_origin[suffix].sum(), total.iloc[0][suffix], f"origen compra {year}")
        close(stores[suffix].sum(), value_for(by_channel,"channel","RETAIL")[suffix], f"tiendas Retail {year}")
        close(by_division[suffix].sum(), total.iloc[0][suffix], f"divisiones {year}")
        close(by_country_division[suffix].sum(), total.iloc[0][suffix], f"pais-divisiones {year}")
        close(by_country_origin[suffix].sum(), total.iloc[0][suffix], f"pais-origen {year}")
        close(by_online_dispatch[suffix].sum(),
              value_for(by_origin,"origin_type","Compra online")[suffix],
              f"distribucion del origen online {year}")
        close(return_rate.loc[return_rate["year"].eq(year), "net_sales_eur"].sum(), total.iloc[0][suffix], f"devoluciones {year}")

    for _, row in stores.iterrows():
        for y in (2025, 2026):
            close(row[f"floor_{y}_eur"] + row[f"ship_{y}_eur"], row[f"q1_{y}_eur"], f"componentes tienda {row['store_spot']} {y}")
        close(row["floor_change_eur"] + row["ship_change_eur"], row["change_eur"], f"variación tienda {row['store_spot']}")

    for year in (2025, 2026):
        subset = return_rate.loc[return_rate["year"].eq(year)]
        close(subset["gross_sales_eur"].sum() - subset["return_sales_eur"].sum(), subset["net_sales_eur"].sum(), f"gross - returns {year}")

    # 5. Informes para trazabilidad; el HTML solo usa estas agregaciones de la fact
    exports = {
        "01_canal": by_channel,
        "02_pais_canal": by_country_channel,
        "03_retail_fulfillment": by_mix,
        "04_tiendas_retail": stores,
        "05_origen_compra": by_origin,
        "06_pais_total": by_country,
        "07_divisiones": by_division,
        "08_devoluciones": return_rate,
        "09_online_despacho": by_online_dispatch,
        "10_pais_origen": by_country_origin,
        "11_pais_division": by_country_division,
    }
    for name, frame in exports.items():
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)

    html = build_html({
        "channel": by_channel,
        "countries": by_country_channel,
        "total": total,
        "origin": by_origin,
        "mix": by_mix,
        "stores": stores,
        "country_total": by_country,
        "divisions": by_division,
        "returns": return_rate,
        "online_dispatch": by_online_dispatch,
        "country_origin": by_country_origin,
        "country_divisions": by_country_division,
    })
    target = OUTPUT / "leadership_presentation.html"
    target.write_text(html, encoding="utf-8")

    print("\n=== PREGUNTA 1. CANALES ===")
    print(by_channel.round(2).to_string(index=False))
    print("\n=== PREGUNTA 1. PAÍS Y CANAL ===")
    print(by_country_channel.round(2).to_string(index=False))
    print("\n=== PREGUNTA 1. VENTAS PRESENCIALES VS. DESPACHO DESDE TIENDA ===")
    print(by_mix.round(2).to_string(index=False))
    print("\n=== PREGUNTA 2. TIENDAS ORDENADAS POR CONTRIBUCIÓN ===")
    print(stores[["country", "store_name", "change_eur", "floor_change_eur", "ship_change_eur"]].round(2).to_string(index=False))
    print("\n=== INSIGHTS. CATEGORÍAS Y DEVOLUCIONES ===")
    print(by_division.round(2).to_string(index=False))
    print(return_rate.round(2).to_string(index=False))
    print("\n=== ORIGEN ONLINE: DESPACHO DC VS TIENDA ===")
    print(by_online_dispatch.round(2).to_string(index=False))
    print("\n=== EXPLICACION POR PAIS Y ORIGEN ===")
    print(by_country_origin.round(2).to_string(index=False))
    print("\n=== EXPLICACION POR PAIS Y PRODUCTO ===")
    print(by_country_division.round(2).to_string(index=False))
    print("\nTodas las validaciones de negocio pasaron.")
    print("HTML listo:", target)
    print("Abrir desde la raíz del proyecto: open outputs/business/leadership_presentation.html")


if __name__ == "__main__":
    main()
