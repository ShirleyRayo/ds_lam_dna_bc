
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
ANALYTICS = ROOT / "data" / "analytics"
AUDIT = ROOT / "outputs" / "audit"

GRAIN = [
    "month",
    "country",
    "channel",
    "store_spot",
    "group_article",
    "fulfilled_by_store_flag"
]


# ==========================================
# 1. LECTURA DE FUENTES LIMPIAS
# ==========================================

def read_clean(name):
    path = CLEAN / f"{name}.parquet"

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run 02_clean.py first."
        )

    return pd.read_parquet(path)


# ==========================================
# 2. VALIDACIONES ANTES Y DESPUES DE JOINS
# ==========================================

def assert_totals_equal(before, after, label):

    if len(before) != len(after):
        raise ValueError(
            f"{label}: row count changed"
        )

    if before["net_qty"].sum() != after["net_qty"].sum():
        raise ValueError(
            f"{label}: net units changed"
        )

    keys = ["country", "currency"]

    a = (
        before.groupby(keys, dropna=False)
        ["net_sales_local"].sum().sort_index()
    )

    b = (
        after.groupby(keys, dropna=False)
        ["net_sales_local"].sum().sort_index()
    )

    if (
        not a.index.equals(b.index)
        or not np.allclose(
            a.to_numpy(),
            b.to_numpy(),
            atol=0.01,
            rtol=0
        )
    ):
        raise ValueError(
            f"{label}: local sales totals changed"
        )

    print(f"\n[JOIN OK] {label}")
    print(f"Rows: {len(before):,} -> {len(after):,}")

    print(
        pd.concat(
            [
                a.rename("local_before"),
                b.rename("local_after")
            ],
            axis=1
        ).to_string()
    )

    if (
        "net_sales_eur" in before.columns
        and "net_sales_eur" in after.columns
    ):
        if not np.isclose(
            before["net_sales_eur"].sum(),
            after["net_sales_eur"].sum(),
            atol=0.01,
            rtol=0
        ):
            raise ValueError(
                f"{label}: EUR sales totals changed"
            )

        print(
            "EUR before / after:",
            round(before["net_sales_eur"].sum(), 2),
            round(after["net_sales_eur"].sum(), 2)
        )


def checked_merge(
    left,
    right,
    on,
    label,
    allow_missing_store=False
):

    if right.duplicated(on).any():
        raise ValueError(
            f"{label}: duplicated master keys"
        )

    joined = left.merge(
        right,
        on=on,
        how="left",
        validate="many_to_one",
        indicator="_join_status"
    )

    missing = joined["_join_status"].eq("left_only")

    if allow_missing_store:
        invalid = (
            missing
            & joined["store_spot"].notna()
        )
    else:
        invalid = missing

    if invalid.any():
        print(
            joined.loc[invalid, on]
            .drop_duplicates()
            .head(10)
        )
        raise ValueError(
            f"{label}: {invalid.sum()} unmatched rows"
        )

    joined = joined.drop(columns="_join_status")

    assert_totals_equal(left, joined, label)

    return joined


# ==========================================
# 3. RECONCILIACION POR CANAL
# ==========================================

def summarize_step(df, channel_col, stage, sign=1):

    summary = (
        df.groupby(channel_col, dropna=False)
        .agg(
            lines=("net_qty", "size"),
            net_qty=("net_qty", "sum"),
            eur=("net_sales_eur", "sum")
        )
        .reset_index()
        .rename(columns={channel_col: "channel"})
    )

    summary["stage"] = stage

    for col in ["lines", "net_qty", "eur"]:
        summary[col] *= sign

    return summary[
        ["stage", "channel", "lines", "net_qty", "eur"]
    ]


def reconcile(all_lines, valid, fact):

    voided = all_lines.loc[all_lines["is_voided"]]

    reclassified = valid.loc[
        valid["source_channel"].eq("ECOM")
        & valid["fulfilled_by_store_flag"]
    ]

    reclassified_to_retail = reclassified.assign(
        target_channel="RETAIL"
    )

    audit = pd.concat(
        [
            summarize_step(
                all_lines,
                "source_channel",
                "01_clean_source"
            ),
            summarize_step(
                voided,
                "source_channel",
                "02_excluded_voided",
                -1
            ),
            summarize_step(
                reclassified,
                "source_channel",
                "03_ecom_to_retail_out",
                -1
            ),
            summarize_step(
                reclassified_to_retail,
                "target_channel",
                "04_ecom_to_retail_in",
                1
            )
        ],
        ignore_index=True
    )

    expected = (
        audit.groupby("channel", as_index=False)
        [["lines", "net_qty", "eur"]].sum()
    )

    actual = (
        fact.groupby("channel", as_index=False)
        [["net_qty", "net_sales_eur"]].sum()
        .rename(
            columns={
                "net_qty": "fact_net_qty",
                "net_sales_eur": "fact_eur"
            }
        )
    )

    result = expected.merge(
        actual,
        on="channel",
        how="outer",
        validate="one_to_one"
    )

    numeric = [
        "lines",
        "net_qty",
        "eur",
        "fact_net_qty",
        "fact_eur"
    ]

    result[numeric] = result[numeric].fillna(0)

    result["diff_qty"] = (
        result["net_qty"] - result["fact_net_qty"]
    )

    result["diff_eur"] = (
        result["eur"] - result["fact_eur"]
    )

    if (
        result["diff_qty"].ne(0).any()
        or not np.allclose(
            result["diff_eur"],
            0,
            atol=0.01,
            rtol=0
        )
    ):
        raise ValueError(
            "Source-to-fact reconciliation failed"
        )

    return audit, result


# ==========================================
# 4. TRANSFORMACION PRINCIPAL
# ==========================================

def main():

    ANALYTICS.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)

    retail = read_clean("retail_sales").assign(
        source_channel="RETAIL"
    )

    ecom = read_clean("ecom_sales").assign(
        source_channel="ECOM"
    )

    stores = read_clean("stores")
    articles = read_clean("articles")
    fx = read_clean("fx_rates")

    # Unificar las dos fuentes transaccionales
    lines = pd.concat(
        [retail, ecom],
        ignore_index=True
    )

    lines["net_sales_local"] = (
        lines["net_sales"].astype("float64")
    )

    lines["reporting_channel"] = (
        lines["reporting_channel"].astype("string")
    )

    required = [
        "calendar_date",
        "country",
        "currency",
        "group_article",
        "net_sales_local",
        "net_qty",
        "is_voided"
    ]

    if lines[required].isna().any().any():
        raise ValueError(
            "Required sales fields contain nulls"
        )

    print(
        f"Input: {len(retail):,} Retail + "
        f"{len(ecom):,} ECOM = {len(lines):,}"
    )

    # --------------------------------------
    # JOIN 1: EXCHANGE RATES
    # --------------------------------------

    lines = checked_merge(
        lines,
        fx[["country", "currency", "units_per_eur"]],
        on=["country", "currency"],
        label="1. FX rates"
    )

    if (
        lines["units_per_eur"].isna().any()
        or lines["units_per_eur"].le(0).any()
    ):
        raise ValueError("Invalid FX rate")

    lines["gross_sales_eur"] = (
        lines["gross_sales_local"]
        / lines["units_per_eur"]
    )

    lines["return_sales_eur"] = (
        lines["return_sales_local"]
        / lines["units_per_eur"]
    )

    lines["net_sales_eur"] = (
        lines["net_sales_local"]
        / lines["units_per_eur"]
    )

    if not np.allclose(
        lines["gross_sales_eur"]
        - lines["return_sales_eur"],
        lines["net_sales_eur"],
        atol=1e-7,
        rtol=0
    ):
        raise ValueError(
            "EUR monetary reconciliation failed"
        )

    # --------------------------------------
    # JOIN 2: STORES
    # --------------------------------------

    lines = checked_merge(
        lines,
        stores[
            [
                "country",
                "store_spot",
                "store_name",
                "city",
                "store_format"
            ]
        ],
        on=["country", "store_spot"],
        label="2. Stores",
        allow_missing_store=True
    )

    # --------------------------------------
    # JOIN 3: ARTICLES
    # --------------------------------------

    lines = checked_merge(
        lines,
        articles[
            [
                "group_article",
                "article_name",
                "product_division",
                "key_category"
            ]
        ],
        on=["group_article"],
        label="3. Articles"
    )

    # --------------------------------------
    # EXCLUIR ANULACIONES DEL RESULTADO
    # --------------------------------------

    valid = lines.loc[
        ~lines["is_voided"]
    ].copy()

    valid["month"] = (
        valid["calendar_date"].dt.strftime("%Y-%m")
    )

    valid["channel"] = valid["reporting_channel"]

    if (
        valid["month"].isna().any()
        or not valid["channel"].isin(
            ["RETAIL", "ECOM"]
        ).all()
    ):
        raise ValueError("Invalid month or channel")

    if valid.loc[
        valid["channel"].eq("ECOM"),
        "store_spot"
    ].notna().any():
        raise ValueError(
            "ECOM records should not have a store"
        )

    if valid.loc[
        valid["channel"].eq("RETAIL"),
        "store_spot"
    ].isna().any():
        raise ValueError(
            "Retail records require a store"
        )

    # --------------------------------------
    # AGRUPACION A LA GRANULARIDAD REQUERIDA
    # --------------------------------------

    fact = (
        valid.groupby(
            GRAIN,
            dropna=False,
            as_index=False
        )
        .agg(
            store_name=("store_name", "first"),
            city=("city", "first"),
            store_format=("store_format", "first"),
            article_name=("article_name", "first"),
            product_division=("product_division", "first"),
            key_category=("key_category", "first"),
            gross_qty=("gross_qty", "sum"),
            return_qty=("return_qty", "sum"),
            net_qty=("net_qty", "sum"),
            gross_sales_eur=("gross_sales_eur", "sum"),
            return_sales_eur=("return_sales_eur", "sum"),
            net_sales_eur=("net_sales_eur", "sum")
        )
    )

    # --------------------------------------
    # VALIDACIONES DE LA FACT
    # --------------------------------------

    if fact.duplicated(GRAIN).any():
        raise ValueError(
            "Duplicate grain in final fact"
        )

    if not (
        fact["gross_qty"] - fact["return_qty"]
        == fact["net_qty"]
    ).all():
        raise ValueError(
            "Fact quantity reconciliation failed"
        )

    if not np.allclose(
        fact["gross_sales_eur"]
        - fact["return_sales_eur"],
        fact["net_sales_eur"],
        atol=1e-7,
        rtol=0
    ):
        raise ValueError(
            "Fact monetary reconciliation failed"
        )

    if not np.isclose(
        valid["net_sales_eur"].sum(),
        fact["net_sales_eur"].sum(),
        atol=0.01,
        rtol=0
    ):
        raise ValueError(
            "Aggregation changed net sales"
        )

    if (
        valid["net_qty"].sum()
        != fact["net_qty"].sum()
    ):
        raise ValueError(
            "Aggregation changed net units"
        )

    # Conciliacion fuente -> fact
    audit, reconciliation = reconcile(
        lines,
        valid,
        fact
    )

    fact = (
        fact.sort_values(
            GRAIN,
            na_position="last"
        )
        .reset_index(drop=True)
    )

    # --------------------------------------
    # PERSISTENCIA
    # --------------------------------------

    destination = (
        ANALYTICS / "fact_sellout_performance.parquet"
    )

    fact.to_parquet(
        destination,
        index=False
    )

    audit.to_csv(
        AUDIT / "reconciliation_steps.csv",
        index=False
    )

    reconciliation.to_csv(
        AUDIT / "reconciliation_by_channel.csv",
        index=False
    )

    print("\n=== FINAL FACT ===")
    print("Valid source lines:", len(valid))
    print("Fact rows:", len(fact))

    print("\n=== RECONCILIATION ===")
    print(reconciliation.to_string(index=False))

    print("\n=== FACT PREVIEW ===")
    print(fact.head(10).to_string(index=False))

    print("\nSaved:", destination)
    print("All validations passed.")


if __name__ == "__main__":
    main()
