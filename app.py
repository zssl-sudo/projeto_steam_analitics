import streamlit as st
from src.data import load_data
from src.filters import sidebar_filters
from src.charts import (
    kpi_cards,
    releases_by_year_chart,
    price_vs_owners_scatter,
    price_by_genre_boxplot,
    top_publishers_bar,
)

st.set_page_config(page_title="Games Analytics Dashboard", layout="wide")

st.title("Panorama do Mercado de Games")
st.caption(
    "Dashboard interativo baseado no dataset games.csv. Filtros na barra lateral."
)

@st.cache_data(show_spinner=False)
def get_data():
    return load_data()

with st.spinner("Carregando e preparando os dados..."):
    df, dim_genres = get_data()

# Sidebar: filtros globais
filters = sidebar_filters(df, dim_genres)

# KPIs principais
kpi_cards(df, filters)

col1, col2 = st.columns((3, 2), gap="large")
with col1:
    releases_by_year_chart(df, filters)
with col2:
    top_publishers_bar(df, filters)

st.subheader("Preço x Popularidade (owners)")
price_vs_owners_scatter(df, filters)

st.subheader("Distribuição de preço por gênero")
price_by_genre_boxplot(df, filters)

st.markdown(
    """
    Dicas de performance:
    - Na primeira execução o CSV é convertido para Parquet automaticamente para leituras futuras mais rápidas.
    - Evite selecionar todos os gêneros ao mesmo tempo se o arquivo for muito grande.
    """
)
