CriticalHitData — Dashboard de Analytics do Mercado de Games (Streamlit)

Resumo
- Este projeto é um dashboard interativo em Streamlit para explorar dados do mercado de games (Steam Games dataset).
- Ele traz KPIs, gráficos e filtros para responder perguntas como: quais gêneros estão em alta, como preço se relaciona com popularidade, quem são as principais publicadoras, e como os lançamentos evoluíram ao longo do tempo.

Principais funcionalidades
- KPIs no topo de cada seção (ex.: total de jogos, preço médio, aceitação média, mediana de proprietários/owners).
- Filtros na barra lateral:
  - Ano de lançamento (limitado aos últimos 10 anos, com base na coluna release_year derivada automaticamente).
  - Faixa de preço (USD).
  - Plataformas (Windows, Mac, Linux).
  - Gêneros (Top 30 mais frequentes).
  - Aceitação mínima (%), calculada a partir de Positive e Negative.
- Seções do dashboard (renderização sob demanda):
  - Visão geral
  - Lançamentos por ano
  - Top publicadoras
  - Preço x Popularidade (owners)
  - Preço por gênero
  - Gêneros: emergentes e em declínio

Pré‑requisitos
- Python 3.10+ recomendado
- pip

Instalação e execução local
1) Clone o repositório e entre na pasta do projeto.
2) (Opcional) Crie e ative um ambiente virtual:
   - Windows (PowerShell):
     - python -m venv .venv
     - .\.venv\Scripts\Activate.ps1
3) Instale as dependências:
   - pip install -r requirements.txt
4) Disponibilize o dataset (veja a próxima seção) e rode o app:
   - streamlit run app.py

Dados — como fornecer o dataset
O app tenta carregar os dados na seguinte ordem de preferência:
1) Arquivo local Parquet (recomendado): data\games.parquet
2) Arquivo local CSV: data\games.csv
3) Opcional: CSV/Parquet remoto via variável de ambiente ou secrets chamada DATA_URL
4) Se existir um CSV pequeno chamado data\games_small.csv, ele tem prioridade para facilitar testes locais

Uso de DATA_URL
- Defina DATA_URL apontando para um arquivo .csv ou .parquet acessível publicamente.
- Exemplos:
  - No Windows (PowerShell): $env:DATA_URL = "https://seuservidor/dados/games.parquet"
  - Em .streamlit/secrets.toml (Streamlit Cloud):
    DATA_URL = "https://seuservidor/dados/games.csv"

Colunas esperadas (mínimo útil)
- Name (ou name): nome do jogo
- Release date: data de lançamento (texto). O ano é derivado automaticamente em release_year
- Genres (ou genres): lista de gêneros (a aplicação aceita string que representa lista e também lista real)
- Estimated owners: string no formato "min - max" para estimativa de proprietários; a aplicação deriva owners_min, owners_max e owners_mid
- Price: preço do jogo em USD (<= 0 indica Free‑to‑Play)
- Positive, Negative: contagem de avaliações positivas/negativas (usado para aceitação%)
- Windows, Mac, Linux: flags booleanas (plataformas disponíveis)
- Publisher (opcional): usado em "Top publicadoras"

Estrutura do projeto
- app.py — aplicação Streamlit (página única com seções)
- src\data.py — carregamento, tipagem e padronização do dataset (inclui derivação de release_year)
- src\filters.py — filtros da barra lateral (ano, preço, plataformas, gêneros, aceitação mínima)
- src\charts.py — componentes de visualização (KPIs e gráficos)
- data\ — pasta sugerida para arquivos locais (games.parquet, games.csv, games_small.csv)
- logo.jpeg — usado como ícone da página e na barra lateral
- requirements.txt — dependências do projeto

Como usar o dashboard
1) Ajuste os filtros na barra lateral para focar o recorte desejado.
2) Escolha a seção a exibir (apenas uma por vez) para melhor performance.
3) Use as métricas e gráficos para identificar padrões e oportunidades (preço x popularidade, gêneros em alta, etc.).

Deploy (Streamlit Community Cloud)
1) Faça o push deste repositório para um provedor Git (GitHub, GitLab, etc.).
2) Crie um app no Streamlit Cloud apontando para app.py.
3) Forneça os dados de uma destas formas:
   - Suba data/games.parquet ou data/games.csv para o repositório.
   - OU defina o secret DATA_URL com o link para CSV/Parquet público.

Solução de problemas
- "Falha ao carregar dados":
  - Verifique se existe data/games.parquet (preferível) ou data/games.csv.
  - Como alternativa, defina DATA_URL (variável de ambiente ou secret) apontando para um CSV/Parquet público.
- Sem anos válidos no filtro: o app tenta derivar release_year. Se o dataset não tiver pistas (ex.: Release date ou ano no Name), ajuste a fonte de dados.
- Performance: preferir Parquet (.parquet) ao invés de CSV para carregamento mais rápido.

Licença
- Este repositório não declara licença explícita. Caso pretenda publicar/redistribuir, adicione um arquivo LICENSE conforme necessário.

Créditos
- Desenvolvido em Streamlit. Nome do dashboard no app: CriticalHitData.