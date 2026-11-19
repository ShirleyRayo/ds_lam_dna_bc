import pandas as pd

df = pd.read_parquet(
    "data/analytics/fact_sellout_performance.parquet"
)

# Filtrar los trimestres solicitados
df_q1 = df[
    df["month"].isin([
        "2025-01", "2025-02", "2025-03",
        "2026-01", "2026-02", "2026-03"
    ])
].copy()

df_q1["year"] = df_q1["month"].str[:4].astype(int)

# Ventas netas por pais y canal
df_pais_canal = (
    df_q1.groupby(
        ["country", "channel", "year"],
        as_index=False
    )["net_sales_eur"]
    .sum()
)

# Ventas por tienda
df_tiendas = (
    df_q1[df_q1["channel"] == "RETAIL"]
    .groupby(
        ["country", "store_name", "year"],
        as_index=False
    )["net_sales_eur"]
    .sum()
)

# Explicacion Retail:
# ventas presenciales vs pedidos enviados desde tienda
df_fulfillment = (
    df_q1[df_q1["channel"] == "RETAIL"]
    .groupby(
        ["year", "fulfilled_by_store_flag"],
        as_index=False
    )["net_sales_eur"]
    .sum()
)