
from collections import Counter
from pathlib import Path
import json

import numpy as np
import pandas as pd


# ==========================================
# 1. CONFIGURACION
# ==========================================

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

SOURCES = (
    "retail_sales",
    "ecom_sales",
    "stores",
    "articles",
    "fx_rates"
)


# ==========================================
# 2. LECTURA Y ESTANDARIZACION
# ==========================================

def load_raw(source):
    with (RAW / f"{source}.json").open(
        encoding="utf-8"
    ) as file:
        return pd.DataFrame(json.load(file))


def standardize_text(df, columns, upper=False):
    for column in columns:
        df[column] = (
            df[column]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
        )

        if upper:
            df[column] = df[column].str.upper()


def parse_accounting_date(values, label):
    text = values.astype("string").str.strip()

    date_iso = pd.to_datetime(
        text,
        format="%Y-%m-%d",
        errors="coerce"
    )

    date_dmy = pd.to_datetime(
        text,
        format="%d/%m/%Y",
        errors="coerce"
    )

    parsed = date_iso.fillna(date_dmy)

    if parsed.isna().any():
        raise ValueError(
            f"Invalid dates in {label}: "
            f"{text[parsed.isna()].head(10).tolist()}"
        )

    alternative_dates = int(
        (date_iso.isna() & date_dmy.notna()).sum()
    )

    return parsed, alternative_dates


# ==========================================
# 3. CORRECCION DE IMPORTES
# ==========================================

def fix_sales_amounts(df, source):
    original = (
        df["net_sales"]
        .astype("string")
        .str.strip()
    )

    numeric = pd.to_numeric(
        original,
        errors="coerce"
    )

    invalid = numeric.isna()

    # Only repair numeric-looking values
    # containing the letter O instead of zero.
    repairable = (
        invalid
        & original.str.fullmatch(
            r"-?[0-9O]+(?:\.[0-9O]+)?"
        ).fillna(False)
        & original.str.contains(
            "O", regex=False
        ).fillna(False)
    )

    if int(invalid.sum()) != int(repairable.sum()):
        raise ValueError(
            f"Unrecognized amounts in {source}: "
            f"{original[invalid & ~repairable].tolist()[:10]}"
        )

    fixed_text = original.mask(
        repairable,
        original.str.replace(
            "O", "0", regex=False
        )
    )

    df["net_sales_repaired"] = repairable.astype(bool)

    df["net_sales"] = pd.to_numeric(
        fixed_text,
        errors="raise"
    ).astype("float64")

    return int(repairable.sum())


# ==========================================
# 4. IDENTIFICACION DE ANULACIONES
# ==========================================

def verify_reversals(df, transaction_col, source):

    reversal = (
        df["reversal_indicator"]
        .eq("X")
        .fillna(False)
    )

    original_ids = set(
        df.loc[
            reversal,
            "original_tran_number"
        ].dropna().tolist()
    )

    is_original = df[transaction_col].isin(
        original_ids
    )

    if is_original.sum() != reversal.sum():
        raise ValueError(
            f"Reversal/original count mismatch: {source}"
        )

    # Validate that the reversing lines match
    # their original records.
    signature_columns = [
        "group_article",
        "size_page",
        "country",
        "store_spot",
        "net_qty",
        "net_sales"
    ]

    def signatures(subset, ref_col):
        values = []

        for _, row in subset.iterrows():
            signature = (
                str(row[ref_col]),
            ) + tuple(
                round(float(row[c]), 2)
                if c == "net_sales"
                else str(row[c])
                for c in signature_columns
            )

            values.append(signature)

        return Counter(values)

    original_signatures = signatures(
        df.loc[is_original],
        transaction_col
    )

    reversal_signatures = signatures(
        df.loc[reversal],
        "original_tran_number"
    )

    if original_signatures != reversal_signatures:
        raise ValueError(
            f"Reversal details do not match: {source}"
        )

    df["is_reversal_line"] = reversal.astype(bool)
    df["is_voided_original"] = is_original.astype(bool)

    df["is_voided"] = (
        reversal | is_original
    ).astype(bool)

    return int(reversal.sum()), int(is_original.sum())


# ==========================================
# 5. LIMPIEZA DE VENTAS
# ==========================================

def clean_sales(source, df):

    df = df.copy()

    # Conservar valores originales para auditoria
    df["sold_qty_raw"] = df["sold_qty"].astype("string")
    df["net_sales_raw"] = df["net_sales"].astype("string")

    is_ecom = source == "ecom_sales"

    transaction_col = (
        "ecom_reference_number"
        if is_ecom else "transaction_number"
    )

    line_col = (
        "sor_itm"
        if is_ecom else "line_number"
    )

    upper_cols = [
        "transaction_type",
        "reversal_indicator",
        "country",
        "currency",
        "group_article"
    ]

    if is_ecom:
        upper_cols += [
            "fulfillment_channel",
            "order_origin"
        ]

    standardize_text(df, upper_cols, upper=True)

    standardize_text(
        df,
        [
            transaction_col,
            "original_tran_number",
            "store_spot",
            "size_page"
        ]
    )

    # Validate business keys and categories.
    if df.duplicated(
        [transaction_col, line_col]
    ).any():
        raise ValueError(
            f"Duplicated transaction key: {source}"
        )

    if not df["transaction_type"].isin(
        ["SALE", "RETURN"]
    ).all():
        raise ValueError(
            f"Unknown transaction type: {source}"
        )

    if not df["reversal_indicator"].dropna().isin(
        ["X"]
    ).all():
        raise ValueError(
            f"Unknown reversal indicator: {source}"
        )

    # Dates
    df["calendar_date"], alternative_dates = (
        parse_accounting_date(
            df["calendar_date"],
            source
        )
    )

    if is_ecom:
        df["consumer_order_date"], _ = (
            parse_accounting_date(
                df["consumer_order_date"],
                "consumer_order_date"
            )
        )

    # Numeric measures
    for measure in (
        "return_qty",
        "return_value",
        "net_qty"
    ):
        df[measure] = pd.to_numeric(
            df[measure],
            errors="raise"
        )

    df["return_qty"] = (
        df["return_qty"].fillna(0).astype("int64")
    )

    df["return_value"] = (
        df["return_value"].fillna(0).astype("float64")
    )

    df["net_qty"] = df["net_qty"].astype("int64")

    # Reconstruct missing sold_qty only where
    # net_qty and return_qty support the calculation.
    sold_numeric = pd.to_numeric(
        df["sold_qty"],
        errors="coerce"
    )

    can_reconstruct = (
        sold_numeric.isna()
        & df["transaction_type"].eq("SALE")
        & df["return_qty"].eq(0)
        & df["net_qty"].ge(0)
    )

    if int(sold_numeric.isna().sum()) != int(
        can_reconstruct.sum()
    ):
        raise ValueError(
            f"Cannot reconstruct sold_qty: {source}"
        )

    sold_numeric.loc[can_reconstruct] = (
        df.loc[can_reconstruct, "net_qty"]
    )

    df["sold_qty_reconstructed"] = (
        can_reconstruct.astype(bool)
    )

    df["sold_qty"] = sold_numeric.astype("int64")

    repaired_sales = fix_sales_amounts(df, source)

    # Validate net units.
    if (
        df["sold_qty"] - df["return_qty"]
        != df["net_qty"]
    ).any():
        raise ValueError(
            f"Quantity reconciliation failed: {source}"
        )

    is_return = df["transaction_type"].eq("RETURN")

    # Returns must subtract their value.
    if not np.isclose(
        df.loc[is_return, "net_sales"],
        -df.loc[is_return, "return_value"],
        atol=0.01,
        rtol=0
    ).all():
        raise ValueError(
            f"Return amount mismatch: {source}"
        )

    if not df.loc[
        ~is_return, "net_sales"
    ].ge(0).all():
        raise ValueError(
            f"Negative sale amount: {source}"
        )

    # Keep gross and return components separate.
    df["gross_qty"] = df["sold_qty"]

    df["gross_sales_local"] = np.where(
        is_return,
        0.0,
        df["net_sales"]
    )

    df["return_sales_local"] = df["return_value"]

    if not np.isclose(
        df["gross_sales_local"]
        - df["return_sales_local"],
        df["net_sales"],
        atol=0.01,
        rtol=0
    ).all():
        raise ValueError(
            f"Sales reconciliation failed: {source}"
        )

    reversals, voided_originals = verify_reversals(
        df,
        transaction_col,
        source
    )

    # Apply the business reporting classification.
    if is_ecom:
        df["fulfilled_by_store_flag"] = (
            df["fulfillment_channel"].eq("STORE")
        )

        if not df["fulfillment_channel"].isin(
            ["STORE", "DC"]
        ).all():
            raise ValueError(
                "Unexpected fulfillment channel"
            )

        invalid_store = (
            (
                df["fulfilled_by_store_flag"]
                & df["store_spot"].isna()
            )
            |
            (
                ~df["fulfilled_by_store_flag"]
                & df["store_spot"].notna()
            )
        )

        if invalid_store.any():
            raise ValueError(
                "Inconsistent ECOM store attribution"
            )

        df["reporting_channel"] = (
            df["fulfilled_by_store_flag"].map({
                True: "RETAIL",
                False: "ECOM"
            })
        )

    else:
        df["fulfilled_by_store_flag"] = False
        df["reporting_channel"] = "RETAIL"

    summary = {
        "source": source,
        "rows": len(df),
        "alternative_dates": alternative_dates,
        "quantity_reconstructed": int(
            can_reconstruct.sum()
        ),
        "sales_amount_repaired": repaired_sales,
        "return_rows": int(is_return.sum()),
        "reversal_lines": reversals,
        "voided_original_lines": voided_originals,
        "voided_lines_total": int(
            df["is_voided"].sum()
        ),
        "store_fulfilled_rows": int(
            df["fulfilled_by_store_flag"].sum()
        )
    }

    return df, summary


# ==========================================
# 6. LIMPIEZA DE MAESTROS
# ==========================================

def clean_master(source, df):

    df = df.copy()

    if source == "stores":
        standardize_text(
            df, ["store_spot", "country"],
            upper=True
        )

        standardize_text(
            df, ["store_name", "city", "store_format"]
        )

        standardize_text(
            df, ["store_format"], upper=True
        )

        key = ["country", "store_spot"]

    elif source == "articles":
        standardize_text(
            df,
            [
                "group_article",
                "product_division",
                "key_category"
            ],
            upper=True
        )

        standardize_text(df, ["article_name"])

        key = ["group_article"]

    else:
        standardize_text(
            df, ["country", "currency"],
            upper=True
        )

        df["units_per_eur"] = pd.to_numeric(
            df["units_per_eur"],
            errors="raise"
        )

        if (
            df["units_per_eur"].isna().any()
            or (df["units_per_eur"] <= 0).any()
        ):
            raise ValueError("Invalid exchange rate")

        key = ["country", "currency"]

    if (
        df.duplicated(key).any()
        or df[key].isna().any().any()
    ):
        raise ValueError(
            f"Invalid master keys: {source}"
        )

    return df


# ==========================================
# 7. EJECUCION Y PERSISTENCIA
# ==========================================

def main():

    CLEAN.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for source in SOURCES:

        raw = load_raw(source)

        if source in ("retail_sales", "ecom_sales"):
            cleaned, audit = clean_sales(source, raw)
            summary_rows.append(audit)
        else:
            cleaned = clean_master(source, raw)

        # No records should disappear in this layer.
        if len(cleaned) != len(raw):
            raise ValueError(
                f"Row count changed: {source}"
            )

        output = CLEAN / f"{source}.parquet"

        cleaned.to_parquet(
            output,
            index=False
        )

        print(
            f"{source}: {len(raw):,} raw -> "
            f"{len(cleaned):,} clean rows"
        )

    report = pd.DataFrame(summary_rows)

    report.to_csv(
        CLEAN / "cleaning_summary.csv",
        index=False
    )

    print("\n=== CLEANING AUDIT ===")
    print(report.to_string(index=False))

    print("\nAll sources cleaned successfully!")


if __name__ == "__main__":
    main()
