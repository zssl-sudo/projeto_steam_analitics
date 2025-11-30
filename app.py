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

def _brand_header():
    st.title("Panorama do Mercado de Games")
    st.caption("Dashboard interativo baseado no dataset Steam Games. Filtros na barra lateral.")

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
try:
    st.sidebar.image("logo.jpeg", width='stretch')
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
        "Lançamentos por ano",
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
    # Texto de boas-vindas e instruções da visão geral
    st.markdown(
        """
        🎮 Bem-vindo ao CriticalHitData
        
        O CriticalHitData é um dashboard interativo criado para revelar, por meio de dados reais, quais fatores determinam o sucesso no mercado de games. Aqui você não trabalha com achismos, você analisa números, padrões e tendências que explicam o comportamento da indústria.
        
        A partir de um conjunto de milhares de jogos, mostramos como preço, gênero, modelo Free-to-Play, aceitação do público e crescimento ao longo dos anos impactam diretamente o desempenho de um game no mercado.
        
        📊 O que você encontra neste dashboard?
        Neste ambiente você pode acompanhar, de forma clara e visual:
        🎯 Quantidade total de jogos analisados
        
        
        💰 Preço médio praticado no mercado
        
        
        ⭐ Aceitação média dos jogadores
        
        
        👥 Mediana de proprietários por jogo
        
        
        📆 Evolução de lançamentos ao longo dos anos
        
        
        Tudo isso com filtros dinâmicos
        
        
        🔍 Como usar o CriticalHitData
        Utilize os filtros laterais para ajustar os dados ao seu foco de análise
        
        
        Escolha a seção desejada (Visão Geral, Preço x Popularidade, Gêneros, Publicadoras, etc.)
        
        
        Observe os gráficos e indicadores para identificar padrões, tendências e oportunidades no mercado de games
        
        
        O CriticalHitData transforma dados em inteligência de mercado para estudantes, desenvolvedores, analistas e entusiastas da indústria de games.
        """
    )
    try:
        st.divider()
    except Exception:
        st.markdown("---")
    _kpis_top()
elif view == "Lançamentos por ano":
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

