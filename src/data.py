import ast
import os
import re
import io
import urllib.request
import numpy as np
import pandas as pd
import streamlit as st
try:
    import pyarrow.parquet as pq  # para fallback de leitura remota de Parquet
except Exception:  # pragma: no cover
    pq = None


DATA_DIR_CANDIDATES = [
    # Preferir dataset pequeno/mocado em produção para tornar o app leve
    "data/games_small.csv",
    "games_small.csv",
    # Fallbacks: dataset completo
    "data/games.csv",
    "games.csv",
]
PARQUET_CANDIDATES = [
    "data/games.parquet",
    "games.parquet",
]

LIST_COLS = [
    "Supported languages",
    "Full audio languages",
    "Categories",
    "Genres",
    "genres",
    "Tags",
]

BOOL_COLS = ["Windows", "Mac", "Linux"]

DTYPE_HINTS = {
    "AppID": "Int64",
    "Peak CCU": "Int64",
    "Required age": "Int64",
    "Price": "float32",
    "Metacritic score": "float32",
    "User score": "float32",
    "Positive": "Int64",
    "Negative": "Int64",
    "Recommendations": "Int64",
}


def _find_first_path(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _parse_list(x):
    """Converte diversos formatos para lista.
    Suporta: "['A','B']" (literal Python) e "A,B" (csv simples).
    """
    if pd.isna(x):
        return []
    s = str(x).strip()
    # Tenta avaliar como literal Python primeiro
    try:
        val = ast.literal_eval(s)
        if isinstance(val, list):
            return val
    except Exception:
        pass
    # Fallback: separar por vírgulas, ponto-e-vírgulas ou pipe
    for sep in [",", ";", "|"]:
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip()]
    return [s] if s else []


def _extract_year_fallback(s):
    """Extrai um ano YYYY da string, com sanidade básica."""
    if pd.isna(s):
        return np.nan
    m = re.search(r"(\d{4})", str(s))
    if m:
        y = int(m.group(1))
        return y if 1970 <= y <= 2100 else np.nan
    return np.nan


def _parse_owners(s):
    # "0 - 20000" -> (0, 20000, 10000)
    if pd.isna(s):
        return np.nan, np.nan, np.nan
    try:
        parts = str(s).replace(",", "").split("-")
        a = int(parts[0].strip())
        b = int(parts[1].strip()) if len(parts) > 1 else a
        return a, b, (a + b) / 2
    except Exception:
        return np.nan, np.nan, np.nan


def _coerce_user_score(x):
    """Converte diferentes formatos de 'User score' para um float na escala 0–10.
    Exemplos suportados:
    - "7.8/10" -> 7.8
    - "76%" -> 7.6
    - "7,8" (vírgula decimal) -> 7.8
    - "0.78" (supõe 0–1) -> 7.8
    - "78" (supõe 0–100) -> 7.8
    Valores fora do intervalo [0, 10] retornam NaN.
    """
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if not s:
        return np.nan
    # normaliza vírgula decimal
    s = s.replace(",", ".")
    # captura primeiro número (inteiro ou decimal)
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return np.nan
    try:
        val = float(m.group(1))
    except Exception:
        return np.nan
    # Se o texto contiver '/10', tratar diretamente como escala 0–10
    if "/10" in s:
        pass  # já está em 0–10
    else:
        # Ajuste de escala heurístico
        if 0 <= val <= 1:
            val = val * 10.0
        elif 10 < val <= 100:
            val = val / 10.0
    # sanidade final
    if not (0 <= val <= 10):
        return np.nan
    return val


DATE_CANDIDATES = [
    # Priorizar colunas com ano explícito
    "Year", "year",
    # Em seguida, datas completas com diversos nomes
    "Release date", "Release Date", "release_date", "ReleaseDate",
    "Date", "date",
    # Fallback adicional: alguns datasets trazem a data em 'Name'/'name'
    "Name", "name",
]


def _derive_release_year(df: pd.DataFrame) -> pd.DataFrame:
    """Garante que df['release_year'] exista e represente corretamente o ano de lançamento,
    detectando automaticamente a coluna de data/ano.
    Também padroniza a coluna 'Release date' quando possível.
    """
    # Escolhe a melhor coluna disponível
    col = next((c for c in DATE_CANDIDATES if c in df.columns), None)
    if col is None:
        df["release_year"] = pd.Series(dtype="Int64")
        return df

    if col.lower() in ("year",):
        # Coluna com o ano diretamente
        years = pd.to_numeric(df[col], errors="coerce")
        df["release_year"] = years.astype("Int64")
        try:
            df["Release date"] = pd.to_datetime(years, format="%Y", errors="coerce")
        except Exception:
            pass
        return df

    # Coluna com data completa (string)
    # Em pandas >= 2.2, usar format="mixed" evita o aviso e lida com formatos mistos.
    raw = df[col].astype(str).str.strip()
    try:
        dt = pd.to_datetime(raw, errors="coerce", format="mixed", cache=True)
    except TypeError:
        # Compatibilidade caso a versão do pandas não suporte format="mixed"
        dt = pd.to_datetime(raw, errors="coerce")
    years = dt.dt.year.astype("float")
    mask = years.isna()
    if mask.any():
        years.loc[mask] = df.loc[mask, col].apply(_extract_year_fallback)
    df["Release date"] = dt
    df["release_year"] = pd.Series(years, dtype="Int64")
    return df


@st.cache_data(show_spinner=False, ttl=600)
def load_data():
    parquet_path = _find_first_path(PARQUET_CANDIDATES)
    csv_path = _find_first_path(DATA_DIR_CANDIDATES)

    # Se existir um CSV pequeno (games_small.csv), priorizamos ele mesmo que exista Parquet
    try:
        if csv_path is not None and os.path.basename(csv_path).lower().startswith("games_small"):
            parquet_path = None
    except Exception:
        pass

    # Helper: URL remoto opcional via secrets/variável de ambiente
    def _get_data_url():
        try:
            # st.secrets pode não existir fora do Streamlit
            if "DATA_URL" in st.secrets:
                return st.secrets["DATA_URL"]
        except Exception:
            pass
        return os.getenv("DATA_URL")

    def _load_remote(url: str) -> pd.DataFrame:
        if not url:
            raise FileNotFoundError("DATA_URL não configurada")
        lower = url.lower()
        if lower.endswith(".parquet"):
            # Tenta com pyarrow primeiro
            try:
                return pd.read_parquet(url, engine="pyarrow")
            except Exception:
                # Fallback: baixar via urllib e ler com pyarrow.parquet
                if pq is None:
                    # Último recurso: tentar o backend padrão do pandas (pode ainda falhar)
                    return pd.read_parquet(url)
                with urllib.request.urlopen(url) as resp:
                    data = resp.read()
                table = pq.read_table(io.BytesIO(data))
                return table.to_pandas()
        # Assume CSV caso contrário
        try:
            return pd.read_csv(url)
        except Exception:
            # Último recurso: tentar engine pyarrow (pode não suportar todos os protocolos)
            return pd.read_csv(url, engine="pyarrow")

    if parquet_path is not None:
        # Leitura tolerante a LFS/arquivos corrompidos
        try:
            df = pd.read_parquet(parquet_path)
        except Exception:
            df = None
    else:
        df = None

    if df is not None:
        # Tentar garantir release_year mesmo vindo de Parquet antigo
        df = _derive_release_year(df)
        # Se ainda não temos anos suficientes e existir CSV, reprocessa a partir do CSV
        if ("release_year" not in df.columns or df["release_year"].dropna().nunique() < 2) and csv_path is not None:
            try:
                tmp_df = pd.read_csv(csv_path, engine="pyarrow")
            except Exception:
                tmp_df = pd.read_csv(csv_path)
            # Reaplica todo o pipeline do bloco CSV abaixo de forma resumida
            for c, t in DTYPE_HINTS.items():
                if c in tmp_df.columns:
                    try:
                        tmp_df[c] = tmp_df[c].astype(t)
                    except Exception:
                        pass
            tmp_df = _derive_release_year(tmp_df)
            _bool_map = {
                "true": True, "1": True, "yes": True, "y": True, "t": True,
                "false": False, "0": False, "no": False, "n": False, "f": False,
            }
            for c in BOOL_COLS:
                if c in tmp_df.columns:
                    try:
                        tmp_df[c] = (
                            tmp_df[c].astype(str).str.strip().str.lower().map(_bool_map)
                            .astype("boolean").fillna(False)
                        )
                    except Exception:
                        try:
                            tmp_df[c] = tmp_df[c].astype("boolean").fillna(False)
                        except Exception:
                            pass
            for c in LIST_COLS:
                if c in tmp_df.columns:
                    tmp_df[c] = tmp_df[c].apply(_parse_list)
            if "Genres" not in tmp_df.columns and "genres" in tmp_df.columns:
                tmp_df["Genres"] = tmp_df["genres"]
            if "Estimated owners" in tmp_df.columns:
                owners_cols = list(zip(*tmp_df["Estimated owners"].apply(_parse_owners)))
                if owners_cols:
                    tmp_df["owners_min"], tmp_df["owners_max"], tmp_df["owners_mid"] = owners_cols
            else:
                tmp_df["owners_min"] = np.nan
                tmp_df["owners_max"] = np.nan
                tmp_df["owners_mid"] = np.nan
            if "Price" in tmp_df.columns:
                tmp_df["is_free"] = (tmp_df["Price"].fillna(0) <= 0.0)
            else:
                tmp_df["Price"] = np.nan
                tmp_df["is_free"] = False
            if "AppID" in tmp_df.columns:
                tmp_df = tmp_df.drop_duplicates(subset=["AppID"])
            if "Name" in tmp_df.columns:
                tmp_df = tmp_df.dropna(subset=["Name"])  
            pos = tmp_df["Positive"].fillna(0) if "Positive" in tmp_df.columns else 0
            neg = tmp_df["Negative"].fillna(0) if "Negative" in tmp_df.columns else 0
            denom = pos + neg
            tmp_df["sentiment_ratio"] = np.where(denom > 0, pos / denom, np.nan)
            if "Genres" in tmp_df.columns:
                tmp_df["primary_genre"] = tmp_df["Genres"].apply(lambda xs: xs[0] if isinstance(xs, list) and len(xs) else "Unknown")
            elif "genres" in tmp_df.columns:
                tmp_df["primary_genre"] = tmp_df["genres"].apply(lambda xs: xs[0] if isinstance(xs, list) and len(xs) else "Unknown")
            else:
                tmp_df["primary_genre"] = "Unknown"
            # Substitui df e regrava parquet otimizado
            df = tmp_df
            target_parquet = PARQUET_CANDIDATES[0]
            try:
                os.makedirs(os.path.dirname(target_parquet), exist_ok=True)
                df.to_parquet(target_parquet, index=False)
            except Exception:
                pass
    elif csv_path is not None:
        # Detecta ponteiro de Git LFS em CSV (não contém dados reais)
        is_lfs_pointer = False
        try:
            with open(csv_path, "rb") as fh:
                head = fh.read(256)
            try:
                head_text = head.decode("utf-8", errors="ignore")
                if "https://git-lfs.github.com/spec/v1" in head_text:
                    is_lfs_pointer = True
            except Exception:
                pass
        except Exception:
            pass

        if is_lfs_pointer:
            df = None
        else:
        # Prefer pyarrow engine if available
            try:
                df = pd.read_csv(csv_path, engine="pyarrow")
            except Exception:
                try:
                    df = pd.read_csv(csv_path)
                except Exception:
                    df = None

        if df is not None:
            # Tipagem básica
            for c, t in DTYPE_HINTS.items():
                if c in df.columns:
                    try:
                        df[c] = df[c].astype(t)
                    except Exception:
                        pass

            # Datas (robusto + detecção automática)
            df = _derive_release_year(df)

            # Booleanos (normaliza strings/0/1 para True/False de forma robusta)
            _bool_map = {
                "true": True, "1": True, "yes": True, "y": True, "t": True,
                "false": False, "0": False, "no": False, "n": False, "f": False,
            }
            for c in BOOL_COLS:
                if c in df.columns:
                    try:
                        df[c] = (
                            df[c]
                            .astype(str)
                            .str.strip()
                            .str.lower()
                            .map(_bool_map)
                            .astype("boolean")
                            .fillna(False)
                        )
                    except Exception:
                        try:
                            df[c] = df[c].astype("boolean").fillna(False)
                        except Exception:
                            pass

            # Listas
            for c in LIST_COLS:
                if c in df.columns:
                    df[c] = df[c].apply(_parse_list)

            # Unificar chave de gêneros para 'Genres'
            if "Genres" not in df.columns and "genres" in df.columns:
                df["Genres"] = df["genres"]

            # Donos
            if "Estimated owners" in df.columns:
                owners_cols = list(zip(*df["Estimated owners"].apply(_parse_owners)))
                if owners_cols:
                    df["owners_min"], df["owners_max"], df["owners_mid"] = owners_cols
            else:
                df["owners_min"] = np.nan
                df["owners_max"] = np.nan
                df["owners_mid"] = np.nan

            # Flags e qualidade
            if "Price" in df.columns:
                df["is_free"] = (df["Price"].fillna(0) <= 0.0)
            else:
                df["Price"] = np.nan
                df["is_free"] = False

            if "AppID" in df.columns:
                df = df.drop_duplicates(subset=["AppID"])
            if "Name" in df.columns:
                df = df.dropna(subset=["Name"])  # mantém NaT em datas

            # Métricas derivadas
            pos = df["Positive"].fillna(0) if "Positive" in df.columns else 0
            neg = df["Negative"].fillna(0) if "Negative" in df.columns else 0
            denom = pos + neg
            df["sentiment_ratio"] = np.where(denom > 0, pos / denom, np.nan)

            # Gênero primário
            if "Genres" in df.columns:
                df["primary_genre"] = df["Genres"].apply(lambda xs: xs[0] if isinstance(xs, list) and len(xs) else "Unknown")
            elif "genres" in df.columns:
                df["primary_genre"] = df["genres"].apply(lambda xs: xs[0] if isinstance(xs, list) and len(xs) else "Unknown")
            else:
                df["primary_genre"] = "Unknown"

            # Salva Parquet otimizado se possível
            target_parquet = PARQUET_CANDIDATES[0]
            try:
                os.makedirs(os.path.dirname(target_parquet), exist_ok=True)
                df.to_parquet(target_parquet, index=False)
            except Exception:
                pass
    else:
        # Nem Parquet nem CSV válidos: tenta URL remota
        url = _get_data_url()
        if url:
            try:
                df = _load_remote(url)
                df = _derive_release_year(df)
                st.caption("Carregado dataset remoto definido em DATA_URL.")
            except Exception:
                df = None
        if df is None:
            # Sem arquivo, retornar DF vazio com colunas mínimas
            st.warning(
                "Nenhum arquivo local encontrado (data/games.parquet ou data/games.csv). "
                "Opcionalmente configure DATA_URL (secrets ou variável de ambiente) para baixar o dataset automaticamente."
            )
            df = pd.DataFrame(columns=[
                "AppID", "Name", "release_year", "Price", "owners_mid", "is_free",
                "User score", "primary_genre", "Publishers"
            ])

    # Garantias pós-carga (CSV ou Parquet): sempre tentar derivar do melhor campo
    # - Se houver menos de 2 anos únicos válidos, tente derivar novamente a partir dos candidatos
    need_rederive = (
        "release_year" not in df.columns
        or df["release_year"].isna().all()
        or df["release_year"].dropna().nunique() < 2
    )
    if need_rederive:
        df = _derive_release_year(df)

    # Normalização robusta de 'User score' para escala 0–10
    try:
        if "User score" in df.columns:
            df.loc[:, "User score"] = df["User score"].apply(_coerce_user_score).astype("float32")
    except Exception:
        # Não interromper o pipeline em caso de esquemas inesperados
        pass

    # Regra de limpeza solicitada:
    # Remover jogos GRATUITOS cuja coluna "Metacritic score" seja exatamente 0.
    # - Considera-se gratuito quando df["is_free"] é True, ou, na ausência dessa coluna,
    #   quando Price <= 0 (com NaN tratado como 0).
    try:
        has_meta = "Metacritic score" in df.columns
        if has_meta:
            # Garante comparação robusta mesmo com strings/NaN
            meta_series = pd.to_numeric(df["Metacritic score"], errors="coerce")
            score_zero = meta_series.fillna(-1) == 0
            # Determina gratuidade
            if "is_free" in df.columns:
                free_mask = df["is_free"].fillna(False).astype(bool)
            elif "Price" in df.columns:
                free_mask = (pd.to_numeric(df["Price"], errors="coerce").fillna(0) <= 0.0)
            else:
                free_mask = pd.Series(False, index=df.index)
            # Aplica filtro: remove onde ambos são verdadeiros
            to_drop = (free_mask & score_zero)
            if to_drop.any():
                df = df[~to_drop]
    except Exception:
        # Em caso de qualquer problema, não interrompe o pipeline
        pass

    # --- Recorte global de anos (últimos N anos) para todo o dashboard ---
    # Aplica o corte após garantir release_year e antes de construir dimensões
    try:
        YEARS_BACK = int(os.getenv("YEARS_BACK", "10"))
    except Exception:
        YEARS_BACK = 10
    if "release_year" in df.columns and df["release_year"].notna().any() and YEARS_BACK > 0:
        try:
            y_max = int(np.nanmax(df["release_year"]))
            y_min_all = int(np.nanmin(df["release_year"]))
            cutoff = max(y_min_all, y_max - YEARS_BACK + 1)
            df = df[df["release_year"].between(cutoff, y_max)]
            try:
                # Só funciona dentro do contexto do Streamlit
                st.caption(f"Exibindo apenas os últimos {YEARS_BACK} anos: {cutoff}–{y_max}.")
            except Exception:
                pass
        except Exception:
            # Se algo falhar, segue sem recorte para não quebrar o fluxo
            pass

    # Garantir 'Genres' unificado e 'primary_genre' disponível mesmo no caminho Parquet
    if "Genres" not in df.columns and "genres" in df.columns:
        df["Genres"] = df["genres"]
    if "primary_genre" not in df.columns:
        if "Genres" in df.columns:
            df["primary_genre"] = df["Genres"].apply(lambda xs: xs[0] if isinstance(xs, list) and len(xs) else "Unknown")
        elif "genres" in df.columns:
            df["primary_genre"] = df["genres"].apply(lambda xs: xs[0] if isinstance(xs, list) and len(xs) else "Unknown")
        else:
            df["primary_genre"] = "Unknown"

    # Dimensão de gêneros para filtros
    # Dimensão de gêneros: aceita 'Genres' ou 'genres'
    genre_col = "Genres" if "Genres" in df.columns else ("genres" if "genres" in df.columns else None)
    if genre_col is not None:
        dim_genres = (
            df.explode(genre_col)[genre_col]
            .dropna().replace("", np.nan)
            .dropna().value_counts().reset_index()
        )
        # Após reset_index, as colunas ficam ['index', genre_col] ou ['index', <series_name>]
        # Garante nomes padronizados
        dim_genres.columns = ["genre", "n"]
    else:
        dim_genres = pd.DataFrame({"genre": [], "n": []})

    # Compactação de dtypes para reduzir memória (útil no deploy)
    # Garante que estamos trabalhando em uma cópia real para evitar SettingWithCopyWarning
    try:
        df = df.copy()
        if "primary_genre" in df.columns:
            df.loc[:, "primary_genre"] = df["primary_genre"].astype("category")
        if "Publishers" in df.columns:
            # Pode ser string; categorias economizam memória
            df.loc[:, "Publishers"] = df["Publishers"].astype("category")
        for c in ["Price", "User score"]:
            if c in df.columns:
                df.loc[:, c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    except Exception:
        pass

    return df, dim_genres
