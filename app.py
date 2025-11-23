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

try:
    with st.spinner("Carregando e preparando os dados..."):
        df, dim_genres = get_data()
except Exception as e:
    import traceback
    st.error("Falha ao carregar dados. Veja detalhes abaixo e configure o dataset para o deploy.")
    st.code("\n".join(traceback.format_exception(e)))
    st.info(
        "Dica: garanta que exista data/games.parquet (recomendado) ou data/games.csv no repositório. "
        "Alternativamente defina DATA_URL (em Secrets ou variável de ambiente) apontando para um CSV/Parquet público."
    )
    st.stop()

if df.empty:
    st.warning(
        "Nenhum dado encontrado. Adicione data/games.parquet ou data/games.csv ao repositório, "
        "ou configure DATA_URL (Secrets/variável de ambiente) com o link para o dataset."
    )

# Sidebar: filtros globais
filters = sidebar_filters(df, dim_genres)

# Sidebar: controle de exibição sob demanda
try:
    st.sidebar.divider()
except Exception:
    st.sidebar.markdown("---")

view = st.sidebar.radio(
    "Seção para exibir",
    [
        "Visão geral",
        "Lançamentos por ano",
        "Top publicadoras",
        "Preço x Popularidade",
        "Preço por gênero",
    ],
    index=0,
    help="Renderize apenas uma seção por vez para deixar a página mais leve.",
)

def _safe_draw(fn, title: str | None = None):
    try:
        if title:
            st.subheader(title)
        fn()
    except Exception as e:
        st.warning(f"Não foi possível renderizar um gráfico: {e}")

# Renderização sob demanda
if view == "Visão geral":
    _safe_draw(lambda: kpi_cards(df, filters))
    st.info("Selecione uma seção na barra lateral para exibir um gráfico específico sob demanda.")
elif view == "Lançamentos por ano":
    _safe_draw(lambda: releases_by_year_chart(df, filters))
elif view == "Top publicadoras":
    _safe_draw(lambda: top_publishers_bar(df, filters))
elif view == "Preço x Popularidade":
    _safe_draw(lambda: price_vs_owners_scatter(df, filters), title="Preço x Popularidade (owners)")
elif view == "Preço por gênero":
    _safe_draw(lambda: price_by_genre_boxplot(df, filters), title="Distribuição de preço por gênero")

st.markdown(
    """
    Dicas de performance:
    - Na primeira execução o CSV é convertido para Parquet automaticamente para leituras futuras mais rápidas.
    - Evite selecionar todos os gêneros ao mesmo tempo se o arquivo for muito grande.
    """
)
