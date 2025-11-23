import os
import streamlit as st
import numpy as np
import pandas as pd


def _safe_min(series, default=0):
    try:
        v = series.replace([np.inf, -np.inf], np.nan).dropna()
        return float(v.min()) if len(v) else default
    except Exception:
        return default


def _safe_max(series, default=1):
    try:
        v = series.replace([np.inf, -np.inf], np.nan).dropna()
        return float(v.max()) if len(v) else default
    except Exception:
        return default


def sidebar_filters(df, dim_genres):
    st.sidebar.header("Filtros")

    # Ano de lançamento
    if "release_year" in df.columns and df["release_year"].notna().any():
        y_min = int(np.nanmin(df["release_year"]))
        y_max = int(np.nanmax(df["release_year"]))
        if y_min < y_max:
            # Por padrão, exibir apenas os últimos N anos (N=10, configurável via YEARS_BACK_DEFAULT)
            years_back_default = int(os.getenv("YEARS_BACK_DEFAULT", "10"))
            lo_default = max(y_min, y_max - years_back_default + 1)
            default_years = (lo_default, y_max)
            # Travar o mínimo do slider no cutoff calculado (lo_default)
            years = st.sidebar.slider("Ano de lançamento", lo_default, y_max, default_years)
            st.sidebar.caption(f"Dashboard limitado aos últimos {years_back_default} anos: {lo_default}–{y_max}.")
        else:
            st.sidebar.caption(f"Ano único no dataset: {y_min}. Filtro de ano desativado.")
            years = (y_min, y_max)
    else:
        years = None

    # Preço
    p_series = df["Price"] if "Price" in df.columns else pd.Series([], dtype=float)
    p_min = _safe_min(p_series, 0.0)
    p_max = _safe_max(p_series, p_min)
    if p_min < p_max:
        price = st.sidebar.slider("Preço (USD)", float(p_min), float(p_max), (float(p_min), float(p_max)))
    else:
        st.sidebar.caption(f"Preço único no dataset: ${p_min:.2f}. Filtro de preço desativado.")
        price = (p_min, p_max)

    # Plataformas
    available_platforms = [c for c in ["Windows", "Mac", "Linux"] if c in df.columns]
    platforms = st.sidebar.multiselect(
        "Plataformas",
        available_platforms,
        default=[],
        help="Selecione uma ou mais. Em branco = todas."
    )

    # Gêneros (top 30) — robusto a diferentes nomes de coluna e à ausência de dim_genres
    if not dim_genres.empty:
        genre_col = "genre" if "genre" in dim_genres.columns else dim_genres.columns[0]
        genre_list = (
            dim_genres.head(30)[genre_col].astype(str).tolist()
        )
    else:
        # fallback direto do DF, aceitando 'Genres' ou 'genres'
        if "Genres" in df.columns:
            genre_list = (
                pd.Series(df["Genres"].explode().dropna().unique()).astype(str).tolist()
            )
        elif "genres" in df.columns:
            genre_list = (
                pd.Series(df["genres"].explode().dropna().unique()).astype(str).tolist()
            )
        else:
            genre_list = []
    top_genres = st.sidebar.multiselect("Gêneros (top 30)", genre_list)

    # Score mínimo
    min_score = st.sidebar.slider("User score mínimo", 0, 100, 0)

    return {
        "years": years,
        "price": price,
        "platforms": platforms,
        "genres": top_genres,
        "min_score": min_score,
    }
