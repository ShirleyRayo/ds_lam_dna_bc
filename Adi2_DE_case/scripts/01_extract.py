
from pathlib import Path
from html import escape
import json
import os

import requests
import pandas as pd


# ==========================================
# 1. CONFIGURACION
# ==========================================

BASE_URL = os.getenv(
    "ADI2_API_URL",
    "http://127.0.0.1:8000"
).rstrip("/")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
EDA_DIR = PROJECT_ROOT / "outputs" / "eda"

PAGE_SIZE = 2000

ENDPOINTS = {
    "retail_sales": "/retail/sales",
    "ecom_sales": "/ecom/sales",
    "stores": "/stores",
    "articles": "/articles",
    "fx_rates": "/fx_rates",
}


# ==========================================
# 2. EXTRACCION PAGINADA
# ==========================================

def fetch_all_pages(
    session: requests.Session,
    endpoint: str
) -> list[dict]:

    records = []
    expected_total = None

    while True:

        response = session.get(
            f"{BASE_URL}{endpoint}",
            params={
                "limit": PAGE_SIZE,
                "skip": len(records)
            },
            timeout=(5, 60)
        )

        response.raise_for_status()

        page = response.json()

        data = page["data"]
        total = page["total"]

        if not isinstance(data, list):
            raise TypeError(
                f"Invalid data structure: {endpoint}"
            )

        if page["count"] != len(data):
            raise ValueError(
                f"Pagination count mismatch: {endpoint}"
            )

        if expected_total is None:
            expected_total = total

        elif expected_total != total:
            raise ValueError(
                f"Total changed during extraction: {endpoint}"
            )

        records.extend(data)

        print(
            f"{endpoint}: "
            f"{len(records):,} / {expected_total:,}"
        )

        if len(records) >= expected_total:
            break

        if not data:
            raise ValueError(
                f"Empty page before extraction ended: {endpoint}"
            )

    if len(records) != expected_total:
        raise ValueError(
            f"Incomplete extraction: {endpoint}"
        )

    return records


# ==========================================
# 3. EXPLORACION INICIAL
# ==========================================

def explore_data(df: pd.DataFrame, name: str):

    print(f"\nDATASET: {name}")

    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    print("\nColumn names:")
    print(df.columns.tolist())

    print("\nData types:")
    print(df.dtypes.to_string())

    print("\nExact duplicate rows:")
    print(df.duplicated().sum())

    print("\nMissing values:")
    print(
        df.isna()
        .sum()
        .sort_values(ascending=False)
        .to_string()
    )

    print("\nFirst 5 records:")
    print(df.head(5).to_string(index=False))


# ==========================================
# 4. DATAFRAMES DE DIAGNOSTICO
# ==========================================

def add_row_number(df: pd.DataFrame):

    # Identifica la posicion original del registro.
    # No modifica el DataFrame RAW.

    numbered = df.reset_index(drop=True).copy()

    numbered.insert(
        0,
        "raw_row",
        range(1, len(numbered) + 1)
    )

    return numbered


def empty_concat(parts):

    if parts:
        return pd.concat(parts, ignore_index=True)

    return pd.DataFrame()


def build_diagnostics(frames):

    summaries = []
    profiles = []

    dates = []
    quantities = []
    amounts = []

    returns = []
    reversals = []
    originals = []
    duplicates = []

    store_orders = []
    fulfillment_counts = []

    business_keys = {
        "retail_sales": [
            "transaction_number", "line_number"
        ],
        "ecom_sales": [
            "ecom_reference_number", "sor_itm"
        ],
        "stores": [
            "country", "store_spot"
        ],
        "articles": [
            "group_article"
        ],
        "fx_rates": [
            "country", "currency"
        ],
    }

    for source, original_df in frames.items():

        df = add_row_number(original_df)

        # ----------------------------------
        # 4.1. Perfilamiento de columnas
        # ----------------------------------

        profile = pd.DataFrame({
            "source": source,
            "column": original_df.columns,
            "dtype": original_df.dtypes.astype(str).values,
            "missing": original_df.isna().sum().values,
            "missing_pct": (
                original_df.isna().mean() * 100
            ).round(2).values,
            "unique_non_null": (
                original_df.nunique(dropna=True).values
            )
        })

        profiles.append(profile)

        # ----------------------------------
        # 4.2. Duplicados por llave
        # ----------------------------------

        key = business_keys[source]

        repeated = df.duplicated(
            subset=key,
            keep=False
        )

        if repeated.any():
            duplicates.append(
                df.loc[repeated].assign(source=source)
            )

        # Contadores para resumen
        irregular_dates = 0
        invalid_quantities = 0
        invalid_amounts = 0
        returned = 0
        reversed_rows = 0
        fulfilled_store = 0

        # ----------------------------------
        # 4.3. Formatos de fecha
        # ----------------------------------

        for col in [
            "calendar_date",
            "consumer_order_date"
        ]:

            if col not in df.columns:
                continue

            values = (
                df[col]
                .astype("string")
                .str.strip()
            )

            # Detecta fechas no expresadas como YYYY-MM-DD.
            # No implica que la fecha sea incorrecta.

            non_iso = (
                values.notna()
                & ~values.str.fullmatch(
                    r"\d{4}-\d{2}-\d{2}"
                ).fillna(False)
            )

            irregular_dates += int(non_iso.sum())

            if non_iso.any():

                dates.append(
                    df.loc[non_iso].assign(
                        source=source,
                        date_field=col,
                        original_value=values[non_iso]
                    )
                )

        # ----------------------------------
        # 4.4. Valores no numericos
        # ----------------------------------

        for col, bucket in [
            ("sold_qty", quantities),
            ("net_sales", amounts)
        ]:

            if col not in df.columns:
                continue

            raw_value = (
                df[col]
                .astype("string")
                .str.strip()
            )

            numeric = pd.to_numeric(
                raw_value,
                errors="coerce"
            )

            invalid = (
                raw_value.notna()
                & numeric.isna()
            )

            if col == "sold_qty":
                invalid_quantities = int(invalid.sum())
            else:
                invalid_amounts = int(invalid.sum())

            if invalid.any():

                bucket.append(
                    df.loc[invalid].assign(
                        source=source,
                        problem_column=col,
                        original_value=raw_value[invalid]
                    )
                )

        # ----------------------------------
        # 4.5. Devoluciones
        # ----------------------------------

        if "transaction_type" in df.columns:

            returned_mask = (
                df["transaction_type"]
                .astype("string")
                .str.strip()
                .str.upper()
                .eq("RETURN")
                .fillna(False)
            )

            returned = int(returned_mask.sum())

            if returned_mask.any():

                returns.append(
                    df.loc[returned_mask].assign(
                        source=source
                    )
                )

        # ----------------------------------
        # 4.6. Reversiones y originales
        # ----------------------------------

        if "reversal_indicator" in df.columns:

            reversed_mask = (
                df["reversal_indicator"]
                .astype("string")
                .str.strip()
                .str.upper()
                .eq("X")
                .fillna(False)
            )

            reversed_rows = int(reversed_mask.sum())

            if reversed_mask.any():

                reversals.append(
                    df.loc[reversed_mask].assign(
                        source=source
                    )
                )

            if source == "retail_sales":
                transaction_col = "transaction_number"

            elif source == "ecom_sales":
                transaction_col = "ecom_reference_number"

            else:
                transaction_col = None

            if transaction_col and reversed_rows:

                original_ids = df.loc[
                    reversed_mask,
                    "original_tran_number"
                ].dropna()

                possible_originals = (
                    df[transaction_col].isin(original_ids)
                )

                if possible_originals.any():

                    originals.append(
                        df.loc[possible_originals].assign(
                            source=source
                        )
                    )

        # ----------------------------------
        # 4.7. Fulfillment ECOM
        # ----------------------------------

        if source == "ecom_sales":

            store_mask = (
                df["fulfillment_channel"]
                .astype("string")
                .str.strip()
                .str.upper()
                .eq("STORE")
                .fillna(False)
            )

            fulfilled_store = int(store_mask.sum())

            if store_mask.any():

                store_orders.append(
                    df.loc[store_mask].assign(
                        source=source
                    )
                )

            fulfillment_counts.append(
                df.groupby(
                    ["country", "fulfillment_channel"],
                    dropna=False
                )
                .size()
                .reset_index(name="rows")
            )

        # ----------------------------------
        # 4.8. Resumen por fuente
        # ----------------------------------

        summaries.append({
            "source": source,
            "rows": len(df),
            "columns": len(original_df.columns),
            "exact_duplicates": int(
                original_df.duplicated().sum()
            ),
            "duplicate_key_rows": int(
                repeated.sum()
            ),
            "non_iso_dates": irregular_dates,
            "non_numeric_sold_qty": invalid_quantities,
            "non_numeric_net_sales": invalid_amounts,
            "return_lines": returned,
            "reversal_lines": reversed_rows,
            "store_fulfilled_lines": fulfilled_store
        })

    # --------------------------------------
    # DataFrames finales del EDA
    # --------------------------------------

    dataframes = {
        "df_resumen": pd.DataFrame(summaries),
        "df_perfil": empty_concat(profiles),
        "df_fechas": empty_concat(dates),
        "df_cantidades": empty_concat(quantities),
        "df_importes": empty_concat(amounts),
        "df_devoluciones": empty_concat(returns),
        "df_reversiones": empty_concat(reversals),
        "df_originales_candidatas": empty_concat(originals),
        "df_duplicados": empty_concat(duplicates),
        "df_fulfillment": empty_concat(fulfillment_counts),
        "df_pedidos_tienda": empty_concat(store_orders),
    }

    return dataframes


# ==========================================
# 5. VISUALIZACION Y EXPORTACION
# ==========================================

def save_eda_report(frames):

    EDA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    dataframes = build_diagnostics(frames)

    print("\n" + "=" * 68)
    print("EXPLORACION DETALLADA - DATOS SIN MODIFICAR")
    print("=" * 68)

    for label, df in dataframes.items():

        print(f"\n{label}: {len(df):,} filas")

        # Mostrar anomalías específicas en consola
        if label in [
            "df_cantidades",
            "df_importes",
            "df_fechas"
        ]:

            cols = [
                c for c in [
                    "source",
                    "raw_row",
                    "transaction_number",
                    "line_number",
                    "calendar_date",
                    "date_field",
                    "original_value",
                    "net_qty",
                    "return_qty",
                    "currency"
                ]
                if c in df.columns
            ]

            if not df.empty:

                print(
                    df[cols]
                    .head(30)
                    .to_string(index=False)
                )

        elif label in [
            "df_resumen",
            "df_fulfillment"
        ]:

            if not df.empty:
                print(df.to_string(index=False))

        elif label == "df_duplicados":

            if not df.empty:
                print(
                    df.head(10).to_string(index=False)
                )

        # Guardar DataFrame completo
        df.to_csv(
            EDA_DIR / f"{label}.csv",
            index=False
        )

    # Exportar tambien todas las fuentes completas
    # para revisarlas visualmente como tablas.

    for source, df in frames.items():

        df.to_csv(
            EDA_DIR / f"full_{source}.csv",
            index=False
        )

    # --------------------------------------
    # 5.1. Reporte HTML
    # --------------------------------------

    css = """
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 28px;
            color: #252b37;
            background: #f5f7fb;
        }

        h1, h2 {
            color: #23385d;
        }

        h2 {
            font-size: 19px;
            margin: 0 0 12px;
        }

        section {
            background: white;
            border: 1px solid #dce3ee;
            padding: 18px;
            border-radius: 10px;
            margin: 18px 0;
        }

        .scroll {
            overflow: auto;
            max-height: 460px;
            border: 1px solid #e4e9ef;
        }

        table {
            border-collapse: collapse;
            font-size: 12px;
            white-space: nowrap;
            width: 100%;
        }

        th, td {
            padding: 8px 11px;
            border-bottom: 1px solid #e4e9ef;
            text-align: left;
        }

        th {
            position: sticky;
            top: 0;
            background: #eaf1fd;
            color: #20385d;
        }

        tr:nth-child(even) {
            background: #f9fbff;
        }

        .hint {
            color: #546275;
            font-size: 13px;
        }
    </style>
    """

    parts = [
        "<!doctype html>",
        "<html lang='es'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<title>Adi2 - Exploracion RAW</title>",
        css,
        "</head>",
        "<body>",
        "<h1>Adi2 | Exploracion inicial de fuentes</h1>",
        (
            "<p class='hint'>Diagnostico de datos RAW. "
            "Ninguna fila ha sido corregida ni eliminada. "
            "raw_row identifica la posicion del registro.</p>"
        ),
        (
            "<p class='hint'>Los nulos pueden ser esperados "
            "segun el tipo de transaccion. Las originales "
            "anuladas son candidatas pendientes de validar "
            "linea por linea.</p>"
        )
    ]

    def section(title, df):

        parts.append(
            f"<section><h2>{escape(title)} "
            f"({len(df):,} registros)</h2>"
        )

        if df.empty:
            parts.append(
                "<p>Sin registros para mostrar.</p>"
            )

        else:
            parts.append("<div class='scroll'>")

            parts.append(
                df.to_html(
                    index=False,
                    border=0,
                    escape=True,
                    na_rep=""
                )
            )

            parts.append("</div>")

        parts.append("</section>")

    # Resumen y perfiles
    section(
        "Resumen general",
        dataframes["df_resumen"]
    )

    section(
        "Perfil de todas las columnas",
        dataframes["df_perfil"]
    )

    # Diagnosticos detallados
    for name in [
        "df_fechas",
        "df_cantidades",
        "df_importes",
        "df_devoluciones",
        "df_reversiones",
        "df_originales_candidatas",
        "df_duplicados",
        "df_fulfillment",
        "df_pedidos_tienda"
    ]:

        section(
            name,
            dataframes[name]
        )

    # Vista inicial de cada fuente
    for name, df in frames.items():

        section(
            f"Vista general {name} - primeras 20 filas",
            df.head(20)
        )

    parts.extend([
        "</body>",
        "</html>"
    ])

    report_path = EDA_DIR / "reporte_eda.html"

    report_path.write_text(
        "\n".join(parts),
        encoding="utf-8"
    )

    print("\nReporte visual:")
    print(report_path)

    print("\nCSV de diagnostico y tablas completas:")
    print(EDA_DIR)

    return dataframes


# ==========================================
# 6. MAIN PIPELINE
# ==========================================

def main():

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    frames = {}

    with requests.Session() as session:

        health_response = session.get(
            f"{BASE_URL}/health",
            timeout=(5, 15)
        )

        health_response.raise_for_status()

        health = health_response.json()
        expected_counts = health["records"]

        print("API status:", health["status"])

        for name, endpoint in ENDPOINTS.items():

            print(f"\nExtracting: {name}")

            records = fetch_all_pages(
                session,
                endpoint
            )

            if len(records) != expected_counts[name]:

                raise ValueError(
                    f"Record count does not match /health: {name}"
                )

            # Persistir datos originales
            output_path = RAW_DIR / f"{name}.json"

            with output_path.open(
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    records,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            # Crear DataFrame
            df = pd.DataFrame(records)

            # Conservarlo para el diagnostico
            frames[name] = df

            explore_data(df, name)

            print(f"\nSaved: {output_path}")

    print("\nExtraction completed successfully!")

    # Ejecutar exploracion adicional
    save_eda_report(frames)


if __name__ == "__main__":
    main()
