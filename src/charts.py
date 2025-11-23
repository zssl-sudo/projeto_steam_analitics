import altair as alt
import streamlit as st
import pandas as pd

# Limitar dados embutidos nos gráficos para evitar payloads gigantes (mais leve em produção)
alt.data_transformers.enable("default", max_rows=15_000)

# Limiares de desempenho (ajuste conforme necessário para o deploy)
MAX_POINTS_SCATTER = 8_000           # máximo de pontos no scatter
TOOLTIP_SWITCH = 2_000               # acima disso, usar tooltips mínimos
TOOLTIP_DISABLE = 10_000             # acima disso, desativar tooltips
HEATMAP_THRESHOLD = 30_000           # acima disso, usar heatmap em vez de scatter
BOX_AGG_THRESHOLD = 50_000           # acima disso, pré-agregar quantis para boxplot


def _apply_filters(df, f):
    q = df.copy()
    # Ano (aplica só se fornecido)
    # Fallback: se o filtro de ano foi definido mas a coluna não existe, tenta derivar
    if f.get("years") is not None and "release_year" not in q.columns:
        try:
            from src.data import _derive_release_year
            q = _derive_release_year(q)
        except Exception:
            pass
    if "release_year" in q.columns and f.get("years") is not None:
        lo, hi = f["years"]
        q = q[(q["release_year"].fillna(0) >= lo) & (q["release_year"].fillna(0) <= hi)]
    # Preço (mantém NaN)
    if "Price" in q.columns and f.get("price") is not None:
        lo, hi = f["price"]
        q = q[q["Price"].isna() | q["Price"].between(lo, hi)]
    # Plataformas: manter linhas com QUALQUER plataforma marcada (OR)
    sel = [p for p in f.get("platforms", []) if p in q.columns]
    if sel:
        q = q[q[sel].any(axis=1)]
    # Gêneros principais
    if f.get("genres"):
        if "primary_genre" in q.columns:
            q = q[q["primary_genre"].isin(f["genres"])]
    # Score mínimo
    if "User score" in q.columns:
        q = q[(q["User score"].fillna(0) >= f.get("min_score", 0))]
    return q


def kpi_cards(df, f):
    q = _apply_filters(df, f)
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Jogos", f"{len(q):,}")
    with col2:
        val = (q.get("is_free", pd.Series([False]*len(q))).astype(float).mean()*100) if len(q) else 0
        st.metric("% Free-to-Play", f"{val:.1f}%")
    with col3:
        med = q.get("Price", pd.Series(dtype=float)).median() if len(q) else 0
        st.metric("Preço mediano", f"${0 if pd.isna(med) else med:.2f}")
    with col4:
        mean_score = q.get("User score", pd.Series(dtype=float)).mean()
        st.metric("User score médio", f"{0 if pd.isna(mean_score) else mean_score:.1f}")
    with col5:
        med_own = q.get("owners_mid", pd.Series(dtype=float)).median()
        st.metric("Owners (mediana)", f"{0 if pd.isna(med_own) else med_own:,.0f}")


def releases_by_year_chart(df, f):
    q = _apply_filters(df, f)
    if "release_year" not in q.columns or q.empty:
        st.info("Sem dados suficientes para exibir lançamentos por ano.")
        return
    year_stats = q.groupby("release_year", as_index=False).agg(
        releases=("AppID", "count"), user_score_mean=("User score", "mean")
    )
    base = alt.Chart(year_stats).encode(x=alt.X("release_year:O", title="Ano"))
    bars = base.mark_bar(color="#3772FF").encode(y=alt.Y("releases:Q", title="Lançamentos"))
    line = base.mark_line(color="#36B37E").encode(y=alt.Y("user_score_mean:Q", title="Score médio"))
    st.altair_chart((bars + line).resolve_scale(y="independent"), width="stretch")


def price_vs_owners_scatter(df, f):
    q = _apply_filters(df, f)
    # Verificações e limpeza de dados essenciais
    if "owners_mid" not in q.columns:
        st.info("Dataset sem coluna 'Estimated owners' → 'owners_mid' não disponível.")
        return
    q = q.dropna(subset=["owners_mid"]).copy()
    if "Price" in q.columns:
        q = q[q["Price"].notna()]
    # Evitar zeros/negativos implausíveis
    q = q[q["owners_mid"] > 0]

    # Garantir coluna de gênero principal
    if "primary_genre" not in q.columns:
        q["primary_genre"] = pd.Series(["Unknown"] * len(q), index=q.index)

    # Se vazio, tenta relaxar filtros (score e gêneros) para garantir exibição
    if q.empty:
        f2 = dict(f)
        f2["min_score"] = 0
        f2["genres"] = []
        q2 = _apply_filters(df, f2).dropna(subset=["owners_mid"]).copy()
        if "Price" in q2.columns:
            q2 = q2[q2["Price"].notna()]
        q2 = q2[q2["owners_mid"] > 0]
        if q2.empty:
            st.info("Sem dados com os filtros atuais (mesmo após relaxar score e gêneros). Refine os filtros.")
            return
        st.caption("Sem dados com os filtros atuais. Exibindo com filtros relaxados (score mínimo 0 e todos os gêneros).")
        q = q2

    total = len(q)

    # Heatmap para casos extremos (reduz drasticamente o payload)
    if total > HEATMAP_THRESHOLD:
        st.caption("Muitos pontos selecionados — exibindo heatmap para melhor desempenho.")
        bins_x = alt.Bin(maxbins=40)
        bins_y = alt.Bin(maxbins=40)
        heat = (
            alt.Chart(q)
            .transform_bin("price_bin", "Price", bin=bins_x)
            .transform_bin("owners_bin", "owners_mid", bin=bins_y)
            .transform_aggregate(count="count()", groupby=["price_bin", "owners_bin"])
            .mark_rect()
            .encode(
                x=alt.X("price_bin:Q", title="Preço (USD)"),
                y=alt.Y("owners_bin:Q", title="Owners (midpoint)"),
                color=alt.Color("count:Q", scale=alt.Scale(scheme="plasma")),
                tooltip=[alt.Tooltip("count:Q", title="Quantidade")],
            )
        )
        st.altair_chart(heat, width="stretch")
        return

    # Downsample para evitar payload excessivo no front-end
    if total > MAX_POINTS_SCATTER:
        q = q.sample(n=MAX_POINTS_SCATTER, random_state=42)
        st.caption(f"Amostrando {MAX_POINTS_SCATTER:,} de {total:,} pontos para desempenho.")

    # Reduzir/Desligar tooltips conforme tamanho
    full_tooltips = [c for c in ["Name", "Price", "owners_mid", "primary_genre", "Publishers", "User score"] if c in q.columns]
    minimal_tooltips = [c for c in ["Name", "Price", "owners_mid", "primary_genre"] if c in q.columns]
    n = len(q)
    if n > TOOLTIP_DISABLE:
        tooltips = []
    elif n > TOOLTIP_SWITCH:
        tooltips = minimal_tooltips
    else:
        tooltips = full_tooltips

    chart = (
        alt.Chart(q)
        .mark_circle(opacity=0.6)
        .encode(
            x=alt.X("Price:Q", title="Preço (USD)", scale=alt.Scale(zero=False)),
            y=alt.Y("owners_mid:Q", title="Owners (midpoint)", scale=alt.Scale(zero=False)),
            color=alt.Color("primary_genre:N", legend=alt.Legend(title="Gênero")),
            size=alt.Size("Recommendations:Q", legend=None, scale=alt.Scale(range=[10, 500])),
            tooltip=tooltips,
        )
    )
    if n <= 3_000:
        chart = chart.interactive()
    st.altair_chart(chart, width="stretch")


def price_by_genre_boxplot(df, f):
    q = _apply_filters(df, f)
    if q.empty or "primary_genre" not in q.columns or "Price" not in q.columns:
        st.info("Sem dados suficientes para exibir boxplots por gênero.")
        return
    top10 = q["primary_genre"].value_counts().head(10).index
    q = q[q["primary_genre"].isin(top10)]

    if len(q) > BOX_AGG_THRESHOLD:
        # Pré-calcula quantis no servidor para reduzir dados enviados
        qs = (
            q.groupby("primary_genre", observed=True)["Price"]
            .quantile([0.0, 0.25, 0.5, 0.75, 1.0])
            .unstack()
            .rename(columns={0.00: "min", 0.25: "q1", 0.50: "med", 0.75: "q3", 1.00: "max"})
            .reset_index()
        )
        base = alt.Chart(qs).encode(x=alt.X("primary_genre:N", sort="-y", title="Gênero"))
        iqr = base.mark_bar(color="#8E6CFF", opacity=0.7).encode(y="q1:Q", y2="q3:Q")
        whisk = base.mark_rule(color="#8E6CFF").encode(y="min:Q", y2="max:Q")
        med = base.mark_tick(color="white", size=20).encode(y="med:Q")
        st.altair_chart(iqr + whisk + med, width="stretch")
        st.caption("Boxplot com quantis pré-calculados para melhor desempenho.")
        return

    chart = alt.Chart(q).mark_boxplot().encode(
        x=alt.X("primary_genre:N", sort="-y", title="Gênero"),
        y=alt.Y("Price:Q", title="Preço"),
        color=alt.Color("primary_genre:N", legend=None),
    )
    st.altair_chart(chart, width="stretch")


def top_publishers_bar(df, f):
    q = _apply_filters(df, f)
    if q.empty or "Publishers" not in q.columns:
        st.info("Sem dados de publishers suficientes.")
        return
    pubs = (
        q.assign(Publisher=q["Publishers"].astype(str).str.split(",").str[0].str.strip())
         .groupby("Publisher", as_index=False)["owners_mid"].sum()
         .sort_values("owners_mid", ascending=False).head(15)
    )
    chart = alt.Chart(pubs).mark_bar(color="#8E6CFF").encode(
        x=alt.X("owners_mid:Q", title="Owners (soma)"),
        y=alt.Y("Publisher:N", sort="-x", title="Publisher"),
        tooltip=["Publisher", alt.Tooltip("owners_mid:Q", format=",.0f")]
    )
    st.altair_chart(chart, width="stretch")
