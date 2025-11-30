import streamlit as st
from src.data import load_data
from src.filters import sidebar_filters
from src.charts import (
    kpi_cards,
    releases_by_year_chart,
    price_vs_owners_scatter,
    price_by_genre_boxplot,
    top_publishers_bar,
    trending_genres_board,
)

# Configuração da página com ícone da marca
st.set_page_config(page_title="Games Analytics Dashboard", page_icon="logo.jpeg", layout="wide")

# Cabeçalho com título (sem exibir a logo na área principal)
def _brand_header():
    st.title("Panorama do Mercado de Games")
    st.caption("Dashboard interativo baseado no dataset games.csv. Filtros na barra lateral.")

_brand_header()

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
# Exibe a logo somente na sidebar (menu de filtros)
try:
    st.sidebar.image("logo.jpeg", use_container_width=True)
except Exception:
    pass

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
        "Top publicadoras",
        "Preço x Popularidade",
        "Preço por gênero",
        "Gêneros: emergentes e em declínio",
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

# Renderiza KPIs no topo de cada seção de gráficos
def _kpis_top():
    try:
        kpi_cards(df, filters)
        try:
            st.divider()
        except Exception:
            st.markdown("---")
    except Exception as e:
        st.warning(f"Falha ao calcular KPIs: {e}")

# Renderização sob demanda
if view == "Visão geral":
    _kpis_top()
    _safe_draw(lambda: releases_by_year_chart(df, filters))
elif view == "Top publicadoras":
    _kpis_top()
    _safe_draw(lambda: top_publishers_bar(df, filters))
elif view == "Preço x Popularidade":
    _kpis_top()
    _safe_draw(lambda: price_vs_owners_scatter(df, filters), title="Preço x Popularidade (owners)")
elif view == "Preço por gênero":
    _kpis_top()
    _safe_draw(lambda: price_by_genre_boxplot(df, filters), title="Distribuição de preço por gênero")
elif view == "Gêneros: emergentes e em declínio":
    _kpis_top()
    _safe_draw(lambda: trending_genres_board(df, filters), title="Gêneros: emergentes e em declínio")

