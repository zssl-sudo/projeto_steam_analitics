import altair as alt
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# Limitar dados embutidos nos gráficos para evitar payloads gigantes (mais leve em produção)
alt.data_transformers.enable("default", max_rows=15_000)

# -----------------------------
# Paleta de cores do dashboard (inspirada no logo)
# Laranja → Coral → Magenta → Roxo
BRAND_CATEGORICAL = [
    "#FF8A00",  # laranja
    "#FF6A3D",  # coral
    "#E43D7A",  # magenta
    "#A12568",  # roxo magentado
    "#6B1E78",  # roxo profundo
]

# Gradiente sequencial para valores contínuos (mapas de calor)
BRAND_SEQUENTIAL = [
    "#FF8A00",
    "#FF6A3D",
    "#FF3D6E",
    "#E43D7A",
    "#A12568",
    "#6B1E78",
]

# Cores de destaque
BRAND_PRIMARY = "#E43D7A"
BRAND_SECONDARY = "#6B1E78"

# Limiares de desempenho (ajuste conforme necessário para o deploy)
MAX_POINTS_SCATTER = 8_000           # máximo de pontos no scatter
TOOLTIP_SWITCH = 2_000               # acima disso, usar tooltips mínimos
TOOLTIP_DISABLE = 10_000             # acima disso, desativar tooltips
HEATMAP_THRESHOLD = 30_000           # acima disso, usar heatmap em vez de scatter
BOX_AGG_THRESHOLD = 50_000           # acima disso, pré-agregar quantis para boxplot


def _ensure_sentiment_ratio(df: pd.DataFrame) -> pd.Series:
    """Retorna uma Series float com a razão de aceitação baseada em Positive/Negative.
    Preferimos a coluna 'sentiment_ratio' se já existir (0–1). Caso contrário,
    calculamos como Positive / (Positive + Negative). Valores com denom=0 viram NaN.
    """
    if "sentiment_ratio" in df.columns:
        try:
            return pd.to_numeric(df["sentiment_ratio"], errors="coerce")
        except Exception:
            pass
    pos = pd.to_numeric(df.get("Positive", pd.Series(index=df.index, dtype=float)), errors="coerce").fillna(0)
    neg = pd.to_numeric(df.get("Negative", pd.Series(index=df.index, dtype=float)), errors="coerce").fillna(0)
    denom = pos + neg
    ratio = pos.div(denom).where(denom > 0)
    return ratio.astype(float)


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
    # Aceitação mínima (%) baseada em Positive/Negative
    try:
        ratio = _ensure_sentiment_ratio(q)
        q = q.assign(acceptance_pct=ratio * 100.0)
        min_pct = f.get("min_acceptance_pct")
        if min_pct is not None and q["acceptance_pct"].notna().any():
            q = q[(q["acceptance_pct"].fillna(-1) >= float(min_pct))]
    except Exception:
        # Se falhar, segue sem filtrar por aceitação
        pass
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
        mean_acc = q.get("acceptance_pct", pd.Series(dtype=float)).mean()
        st.metric("Aceitação média (%)", f"{0 if pd.isna(mean_acc) else mean_acc:.1f}%")
    with col5:
        med_own = q.get("owners_mid", pd.Series(dtype=float)).median()
        st.metric("Owners (mediana)", f"{0 if pd.isna(med_own) else med_own:,.0f}")


def releases_by_year_chart(df, f):
    q = _apply_filters(df, f)
    if q.empty:
        st.info("Sem dados suficientes para exibir lançamentos por ano.")
        return

    # Estratégia corrigida: priorizar 'release_year' e restringir a anos plausíveis
    years_series = None

    # 1) Usa release_year se existir e tiver valores
    if "release_year" in q.columns and q["release_year"].notna().any():
        years_series = pd.to_numeric(q["release_year"], errors="coerce")

    # 2) Caso contrário, tenta derivar no ato a partir de 'Release date' e outros campos
    if years_series is None or pd.isna(years_series).all():
        try:
            from src.data import _derive_release_year
            q2 = _derive_release_year(q.copy())
            cand = pd.to_numeric(q2.get("release_year"), errors="coerce")
            if cand.notna().any():
                years_series = cand
        except Exception:
            years_series = None

    # 3) Último recurso: extrair do título (Name/name)
    if years_series is None or pd.isna(years_series).all():
        name_col = "Name" if "Name" in q.columns else ("name" if "name" in q.columns else None)
        if name_col is not None:
            raw = q[name_col].astype(str).str.strip()
            try:
                dt = pd.to_datetime(raw, errors="coerce", format="mixed", cache=True)
            except TypeError:
                dt = pd.to_datetime(raw, errors="coerce")
            cand = dt.dt.year.astype("float")
            mask_na = cand.isna()
            if mask_na.any():
                import re as _re
                cand.loc[mask_na] = raw[mask_na].apply(
                    lambda s: int(_re.search(r"(\d{4})", s).group(1)) if _re.search(r"(\d{4})", s) else float("nan")
                )
            years_series = cand

    # Se ainda assim não houver anos válidos, aborta
    if years_series is None or pd.isna(years_series).all():
        st.info("Não foi possível identificar o ano de lançamento.")
        return

    # Limpeza final: descartar anos fora de uma faixa plausível e do ano atual
    current_year = datetime.now().year
    years_series = pd.to_numeric(years_series, errors="coerce")
    years_series = years_series.where((years_series >= 1970) & (years_series <= current_year))
    years_series = years_series.astype("Int64")

    if years_series.dropna().empty:
        st.info("Não há anos plausíveis para exibir após a limpeza dos dados.")
        return

    # Agregação: contagem de lançamentos por ano
    year_stats = (
        pd.DataFrame({"year": years_series})
        .dropna()
        .groupby("year", as_index=False)
        .agg(releases=("year", "size"))
        .sort_values("year")
    )

    chart = (
        alt.Chart(year_stats)
        .mark_bar(color=BRAND_PRIMARY)
        .encode(
            x=alt.X("year:O", title="Ano"),
            y=alt.Y("releases:Q", title="Lançamentos")
        )
    )
    st.altair_chart(chart, width="stretch")


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

    # Se vazio, tenta relaxar filtros (aceitação e gêneros) para garantir exibição
    if q.empty:
        f2 = dict(f)
        f2["min_acceptance_pct"] = 0
        f2["genres"] = []
        q2 = _apply_filters(df, f2).dropna(subset=["owners_mid"]).copy()
        if "Price" in q2.columns:
            q2 = q2[q2["Price"].notna()]
        q2 = q2[q2["owners_mid"] > 0]
        if q2.empty:
            st.info("Sem dados com os filtros atuais (mesmo após relaxar aceitação e gêneros). Refine os filtros.")
            return
        st.caption("Sem dados com os filtros atuais. Exibindo com filtros relaxados (aceitação mínima 0% e todos os gêneros).")
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
                color=alt.Color("count:Q", scale=alt.Scale(range=BRAND_SEQUENTIAL)),
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
    # Garante coluna de aceitação para tooltip
    if "acceptance_pct" not in q.columns:
        q = q.assign(acceptance_pct=_ensure_sentiment_ratio(q) * 100.0)
    full_tooltips = [c for c in ["Name", "Price", "owners_mid", "primary_genre", "Publishers", "acceptance_pct"] if c in q.columns]
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
            color=alt.Color(
                "primary_genre:N",
                legend=alt.Legend(title="Gênero"),
                scale=alt.Scale(range=BRAND_CATEGORICAL),
            ),
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
        iqr = base.mark_bar(color=BRAND_SECONDARY, opacity=0.7).encode(y="q1:Q", y2="q3:Q")
        whisk = base.mark_rule(color=BRAND_SECONDARY).encode(y="min:Q", y2="max:Q")
        med = base.mark_tick(color="white", size=20).encode(y="med:Q")
        st.altair_chart(iqr + whisk + med, width="stretch")
        st.caption("Boxplot com quantis pré-calculados para melhor desempenho.")
        return

    chart = alt.Chart(q).mark_boxplot().encode(
        x=alt.X("primary_genre:N", sort="-y", title="Gênero"),
        y=alt.Y("Price:Q", title="Preço"),
        color=alt.Color("primary_genre:N", legend=None, scale=alt.Scale(range=BRAND_CATEGORICAL)),
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
    chart = alt.Chart(pubs).mark_bar(color=BRAND_SECONDARY).encode(
        x=alt.X("owners_mid:Q", title="Owners (soma)"),
        y=alt.Y("Publisher:N", sort="-x", title="Publisher"),
        tooltip=["Publisher", alt.Tooltip("owners_mid:Q", format=",.0f")]
    )
    st.altair_chart(chart, width="stretch")


def trending_genres_board(df: pd.DataFrame, f: dict, top_n: int = 7, window_years: int = 5):
    """Exibe dois gráficos lado a lado destacando gêneros emergentes e em declínio.
    A tendência é estimada pelo coeficiente angular (slope) da participação anual (share) do gênero
    ao longo de uma janela recente de anos.

    - emergentes: maiores slopes positivos (p.p. por ano)
    - em declínio: menores slopes (negativos)
    """
    # Aplicar filtros, mas ignorar pré-seleção de gêneros para não enviesar a tendência
    f2 = dict(f)
    f2["genres"] = []
    q = _apply_filters(df, f2)

    # Garantir ano e gênero disponíveis
    if ("release_year" not in q.columns) or (not q["release_year"].notna().any()):
        try:
            from src.data import _derive_release_year
            q = _derive_release_year(q.copy())
        except Exception:
            pass

    if q.empty or "primary_genre" not in q.columns or ("release_year" not in q.columns):
        st.info("Sem dados suficientes para calcular tendências de gêneros.")
        return

    q = q[q["release_year"].notna()].copy()
    if q.empty:
        st.info("Sem anos válidos após filtros para calcular tendências de gêneros.")
        return

    # Agregar contagem por ano e gênero, depois normalizar por total anual (share)
    grp = (
        q.groupby(["release_year", "primary_genre"], observed=True)
        .size()
        .reset_index(name="n")
    )
    if grp.empty:
        st.info("Sem combinações de ano e gênero para análise de tendência.")
        return

    totals = grp.groupby("release_year", as_index=False)["n"].sum().rename(columns={"n": "total"})
    m = grp.merge(totals, on="release_year", how="left")
    m["share"] = m["n"].div(m["total"].replace(0, np.nan))
    m = m.dropna(subset=["share"])  # descarta anos sem total válido
    if m.empty:
        st.info("Não foi possível calcular participação por ano.")
        return

    # Restringir à janela mais recente de anos
    years_sorted = sorted(m["release_year"].unique())
    if len(years_sorted) < 2:
        st.info("Poucos anos disponíveis para estimar tendência.")
        return
    k = min(window_years, len(years_sorted))
    last_years = years_sorted[-k:]
    m = m[m["release_year"].isin(last_years)].copy()

    # Pivot para preencher ausências como 0 (sem lançamentos => share 0)
    pivot = (
        m.pivot(index="release_year", columns="primary_genre", values="share")
        .fillna(0.0)
        .sort_index()
    )
    if pivot.shape[0] < 2:
        st.info("Número insuficiente de anos na janela para estimar tendência.")
        return

    x = pivot.index.values.astype(float)
    start_year, end_year = int(x[0]), int(x[-1])
    start_shares = pivot.iloc[0]
    end_shares = pivot.iloc[-1]

    slopes = []
    for genre in pivot.columns:
        y = pivot[genre].values.astype(float)
        if np.allclose(y, 0):
            s = 0.0
        else:
            try:
                s = float(np.polyfit(x, y, 1)[0])  # variação por ano (fração/ano)
            except Exception:
                s = 0.0
        slopes.append({
            "primary_genre": genre,
            "slope_ppy": s * 100.0,  # pontos percentuais por ano
            "start_pct": float(start_shares.get(genre, 0.0) * 100.0),
            "end_pct": float(end_shares.get(genre, 0.0) * 100.0),
        })

    df_slopes = pd.DataFrame(slopes)
    if df_slopes.empty:
        st.info("Não foi possível estimar tendências com os dados atuais.")
        return

    emerg = df_slopes.sort_values("slope_ppy", ascending=False).head(top_n)
    decl = df_slopes.sort_values("slope_ppy", ascending=True).head(top_n)

    # Layout lado a lado
    col1, col2 = st.columns(2)
    tooltip_cols = [
        alt.Tooltip("primary_genre:N", title="Gênero"),
        alt.Tooltip("slope_ppy:Q", title="Tendência (p.p./ano)", format=".2f"),
        alt.Tooltip("start_pct:Q", title=f"{start_year} (%)", format=".1f"),
        alt.Tooltip("end_pct:Q", title=f"{end_year} (%)", format=".1f"),
    ]

    with col1:
        st.markdown("#### Emergentes")
        if emerg.empty or emerg["slope_ppy"].le(0).all():
            st.info("Nenhum gênero com tendência de alta na janela analisada.")
        else:
            chart_e = (
                alt.Chart(emerg)
                .mark_bar(color=BRAND_PRIMARY)
                .encode(
                    x=alt.X("slope_ppy:Q", title="p.p. por ano", scale=alt.Scale(zero=False)),
                    y=alt.Y("primary_genre:N", sort="-x", title="Gênero"),
                    tooltip=tooltip_cols,
                )
            )
            st.altair_chart(chart_e, width="stretch")

    with col2:
        st.markdown("#### Em declínio")
        if decl.empty or decl["slope_ppy"].ge(0).all():
            st.info("Nenhum gênero com tendência de queda na janela analisada.")
        else:
            chart_d = (
                alt.Chart(decl)
                .mark_bar(color=BRAND_SECONDARY)
                .encode(
                    x=alt.X("slope_ppy:Q", title="p.p. por ano", scale=alt.Scale(zero=False)),
                    y=alt.Y("primary_genre:N", sort="x", title="Gênero"),
                    tooltip=tooltip_cols,
                )
            )
            st.altair_chart(chart_d, width="stretch")

    st.caption(f"Janela analisada: {start_year}–{end_year}. Tendências medidas em pontos percentuais por ano da participação anual de lançamentos.")
