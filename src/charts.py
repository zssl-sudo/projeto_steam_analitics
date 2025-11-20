import altair as alt
import streamlit as st
import pandas as pd

alt.data_transformers.disable_max_rows()


def _apply_filters(df, f):
    q = df.copy()
    # Ano (aplica só se fornecido)
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
    st.altair_chart((bars + line).resolve_scale(y="independent"), use_container_width=True)


def price_vs_owners_scatter(df, f):
    q = _apply_filters(df, f)
    if "owners_mid" not in q.columns or q["owners_mid"].dropna().empty:
        st.info("Sem dados de owners para o gráfico de dispersão.")
        return
    q = q.dropna(subset=["owners_mid"]).copy()
    q["primary_genre"] = q.get("primary_genre", pd.Series(["Unknown"]*len(q)))
    chart = alt.Chart(q).mark_circle(opacity=0.6).encode(
        x=alt.X("Price:Q", title="Preço (USD)", scale=alt.Scale(zero=False)),
        y=alt.Y("owners_mid:Q", title="Owners (midpoint)", scale=alt.Scale(zero=False)),
        color=alt.Color("primary_genre:N", legend=alt.Legend(title="Gênero")),
        size=alt.Size("Recommendations:Q", legend=None, scale=alt.Scale(range=[10, 500])),
        tooltip=[c for c in ["Name", "Price", "owners_mid", "primary_genre", "Publishers", "User score"] if c in q.columns]
    ).interactive()
    st.altair_chart(chart, use_container_width=True)


def price_by_genre_boxplot(df, f):
    q = _apply_filters(df, f)
    if q.empty or "primary_genre" not in q.columns or "Price" not in q.columns:
        st.info("Sem dados suficientes para exibir boxplots por gênero.")
        return
    top10 = q["primary_genre"].value_counts().head(10).index
    q = q[q["primary_genre"].isin(top10)]
    chart = alt.Chart(q).mark_boxplot().encode(
        x=alt.X("primary_genre:N", sort="-y", title="Gênero"),
        y=alt.Y("Price:Q", title="Preço"),
        color=alt.Color("primary_genre:N", legend=None)
    )
    st.altair_chart(chart, use_container_width=True)


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
    st.altair_chart(chart, use_container_width=True)
