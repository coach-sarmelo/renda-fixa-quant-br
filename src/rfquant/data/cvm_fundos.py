"""Provider de dados de fundos de investimento da CVM.

Baixa os arquivos de Informe Diário do portal de Dados Abertos da CVM
(https://dados.cvm.gov.br/dataset/fi-doc-inf_diario) e disponibiliza
em DataFrames pandas.

Forma do contrato: provider de série com
**contrato próprio** — NÃO herda a ABC ``DataProvider``
(``titulos_disponiveis``/``historico_taxas`` descrevem títulos, não informes
de fundos; forçar a herança distorceria o contrato).

Estrutura dos arquivos:
    https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_YYYYMM.zip

Cada ZIP contém um CSV (``;``, latin-1) com o layout vigente de
classes/subclasses (RCVM 175; os antigos ``TP_FUNDO``/``CNPJ_FUNDO`` não
existem mais na fonte — captura de 2026-09-23):
    TP_FUNDO_CLASSE, CNPJ_FUNDO_CLASSE, ID_SUBCLASSE, DT_COMPTC, VL_TOTAL,
    VL_QUOTA, VL_PATRIM_LIQ, CAPTC_DIA, RESG_DIA, NR_COTST

Fixtures de teste: ``tests/fixtures/cvm_informe_sample.zip`` (reconstruída de
forma determinística — ver sidecar ``cvm_informe_sample.README.md``).

Todo fetch passa por ``rfquant.data.cache`` (diskcache/SQLite) com TTL
explícito de 24 h — o informe troca 1×/dia útil intramês e congela no
fechamento do mês — e ``User-Agent`` explícito (UA de biblioteca
sofre filtro em fontes públicas). Este TTL substitui o antigo cache de arquivo
sem expiração (``~/.rfquant/cache/cvm`` crescia sem limite e nunca
vencia). O frame mensal PARSEADO também é cacheado, além do ZIP cru (mesmo
TTL) — o ``read_csv`` do informe integral roda no cache miss, não a cada
chamada.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pandas as pd
import requests

from rfquant.data import cache
from rfquant.data.cache import USER_AGENT
from rfquant.data.sgs_bcb import SGSProvider

CVM_BASE_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS"
TTL_CVM = 86_400  # 24 h: o informe mensal troca 1×/dia útil e congela no fechamento
TIMEOUT_CVM = 120  # payload ~11 MB/mês — 120 s folgam

# Nomes amigáveis em português (layout vigente de classes/subclasses — RCVM 175)
COLUNAS_PT = {
    "TP_FUNDO_CLASSE": "tipo_fundo",
    "CNPJ_FUNDO_CLASSE": "cnpj_fundo",
    "ID_SUBCLASSE": "id_subclasse",
    "DT_COMPTC": "data_competencia",
    "VL_TOTAL": "valor_total",
    "VL_QUOTA": "valor_cota",
    "VL_PATRIM_LIQ": "patrimonio_liquido",
    "CAPTC_DIA": "captacao_dia",
    "RESG_DIA": "resgate_dia",
    "NR_COTST": "numero_cotistas",
}


class InformeNaoDisponivel(RuntimeError):
    """O arquivo do mês não está publicado na fonte (HTTP 4xx) — erro de
    domínio do provider, distinto de falha de rede: o informe de um mês
    ainda não publicado (a CVM publica D+1) não existe no portal. Subclasse
    de ``RuntimeError`` por compatibilidade com quem já capturava a exceção
    anterior deste módulo."""


class RedeIndisponivel(RuntimeError):
    """Falha de rede ao obter o informe (timeout, DNS, HTTP 5xx) — a
    ``requests.RequestException`` original segue encadeada em ``__cause__``.
    Subclasse de ``RuntimeError`` pelo mesmo motivo de `InformeNaoDisponivel`."""


def _somente_digitos(cnpj: str) -> str:
    """Normaliza um CNPJ mantendo apenas os dígitos (formatação fora do contrato).

    A comparação de CNPJ é por **igualdade normalizada**: ``"00.017.024/0001-53"``
    e ``"00017024000153"`` são o mesmo fundo; uma raiz parcial ou um dígito
    verificador diferente não casa nada.
    """
    return "".join(filter(str.isdigit, cnpj))


class CVMFundosProvider:
    """Acesso aos informes diários de fundos de investimento da CVM.

    Args:
        ttl: TTL do cache em segundos (padrão 24 h — informe diário, D+1).

    Uso::

        df = CVMFundosProvider().informe_diario(2026, 8, cnpj="00.017.024/0001-53")
    """

    def __init__(self, ttl: int = TTL_CVM) -> None:
        self.ttl = ttl

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def informe_diario(
        self,
        ano: int,
        mes: int,
        cnpj: str | None = None,
        usar_cache: bool = True,
    ) -> pd.DataFrame:
        """Retorna o informe diário de fundos para um mês específico.

        Args:
            ano: Ano de referência (ex: 2026).
            mes: Mês de referência (1-12).
            cnpj: Se informado, filtra apenas o fundo com esse CNPJ
                (igualdade normalizada — só dígitos; formatação é indiferente).
            usar_cache: Se True, consulta o cache TTL antes de baixar; se False,
                força o re-download e atualiza o cache.

        Returns:
            DataFrame com colunas renomeadas em português, ordenado por
            (cnpj_fundo, data_competencia) crescente.

        Raises:
            InformeNaoDisponivel: mês sem arquivo publicado na fonte (HTTP 4xx).
            RedeIndisponivel: falha de rede — a causa original segue encadeada.
            ValueError: mês fora de 1-12 ou payload ilegível (ZIP sem entradas).
        """
        if not (1 <= mes <= 12):
            raise ValueError("Mês deve estar entre 1 e 12.")

        url = self._url_mes(ano, mes)

        def _construir() -> pd.DataFrame:
            zip_bytes = self._baixar_zip(ano, mes, usar_cache=usar_cache)
            csv_bytes = self._extrair_csv(zip_bytes)
            df_mes = pd.read_csv(
                io.BytesIO(csv_bytes),
                sep=";",
                encoding="latin-1",
                dtype={"CNPJ_FUNDO_CLASSE": str},
            )
            df_mes = df_mes.rename(columns=COLUNAS_PT)
            if "data_competencia" in df_mes.columns:
                df_mes["data_competencia"] = pd.to_datetime(df_mes["data_competencia"]).dt.date
            return df_mes.sort_values(["cnpj_fundo", "data_competencia"]).reset_index(drop=True)

        df = cache.obter_ou_parsear_frame(
            url, ttl=self.ttl, construtor=_construir, usar_cache=usar_cache
        )

        if cnpj:
            cnpj_alvo = _somente_digitos(cnpj)
            mascara = df["cnpj_fundo"].astype(str).str.replace(r"\D", "", regex=True) == cnpj_alvo
            df = df[mascara].reset_index(drop=True)
        return df

    def historico_fundo(
        self,
        cnpj: str,
        inicio: date,
        fim: date,
        usar_cache: bool = True,
    ) -> pd.DataFrame:
        """Retorna o histórico de um fundo entre duas datas.

        Baixa os informes mensais necessários e concatena. A série sai
        ordenada por ``data_competencia`` crescente.

        Raises:
            InformeNaoDisponivel: qualquer mês do intervalo sem arquivo
                publicado na fonte (HTTP 4xx) — erro explícito propagado:
                nada de engolir exceção; um buraco silencioso na série
                viraria número errado a jusante.
            RedeIndisponivel: falha de rede em qualquer mês do intervalo.
        """
        if inicio > fim:
            raise ValueError("Data inicial deve ser anterior à final.")

        frames: list[pd.DataFrame] = []
        ano, mes = inicio.year, inicio.month
        while (ano, mes) <= (fim.year, fim.month):
            frames.append(self.informe_diario(ano, mes, cnpj=cnpj, usar_cache=usar_cache))
            mes += 1
            if mes > 12:
                mes = 1
                ano += 1

        df = pd.concat(frames, ignore_index=True)
        df = df[
            (pd.to_datetime(df["data_competencia"]) >= pd.Timestamp(inicio))
            & (pd.to_datetime(df["data_competencia"]) <= pd.Timestamp(fim))
        ].reset_index(drop=True)
        return df.sort_values("data_competencia").reset_index(drop=True)

    def listar_fundos(self, ano: int, mes: int) -> pd.DataFrame:
        """Lista todos os fundos com informe no mês, com dados cadastrais básicos."""
        df = self.informe_diario(ano, mes)
        if df.empty:
            return df
        ultimo = df["data_competencia"].max()
        df_ultimo = df[df["data_competencia"] == ultimo]
        return (
            df_ultimo[
                ["cnpj_fundo", "tipo_fundo", "patrimonio_liquido", "numero_cotistas", "valor_cota"]
            ]
            .dropna(subset=["cnpj_fundo"])
            .sort_values("patrimonio_liquido", ascending=False)
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _url_mes(self, ano: int, mes: int) -> str:
        return f"{CVM_BASE_URL}/inf_diario_fi_{ano}{mes:02d}.zip"

    def _baixar_zip(self, ano: int, mes: int, usar_cache: bool = True) -> bytes:
        """Conteúdo cru do ZIP mensal: cache TTL → rede."""
        url = self._url_mes(ano, mes)

        if usar_cache:
            cached: bytes | None = cache.get(url)
            if cached is not None:
                return cached

        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_CVM,
            )
            resp.raise_for_status()
        except requests.RequestException as erro:
            status = getattr(getattr(erro, "response", None), "status_code", None)
            if isinstance(status, int) and 400 <= status < 500:
                raise InformeNaoDisponivel(
                    f"O informe diário da CVM para {mes:02d}/{ano} não está "
                    f"disponível na fonte ({url}): o mês pode ainda não ter "
                    f"sido publicado (a publicação é D+1)."
                ) from erro
            raise RedeIndisponivel(
                f"Falha ao obter o informe diário da CVM para {mes:02d}/{ano} ({url}): {erro}"
            ) from erro

        conteudo = resp.content
        cache.set(url, conteudo, ttl=self.ttl)
        return conteudo

    @staticmethod
    def _extrair_csv(zip_bytes: bytes) -> bytes:
        """CSV de informe dentro do ZIP (um único CSV, normalmente)."""
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            nomes = zf.namelist()
            if not nomes:
                raise ValueError(f"ZIP vazio ({len(zip_bytes)} bytes recebidos).")
            csv_name = next((n for n in nomes if n.lower().endswith(".csv")), nomes[0])
            with zf.open(csv_name) as f:
                return f.read()


# ----------------------------------------------------------------------
# Delegadores de compatibilidade (a implementação vive em comparison)
# ----------------------------------------------------------------------
def rentabilidade_periodo(df_fundo: pd.DataFrame) -> float:
    """Calcula a rentabilidade acumulada a partir da série de cota."""
    from rfquant.comparison import taxa_equivalente

    return taxa_equivalente.rentabilidade_periodo(df_fundo)


def cdi_equivalente(rentabilidade: float, dias_uteis: int) -> float:
    """Anualiza uma rentabilidade pelo número de dias úteis (base 252)."""
    from rfquant.comparison import taxa_equivalente

    return taxa_equivalente.cdi_equivalente(rentabilidade, dias_uteis)


def rentabilidade_anualizada(df_fundo: pd.DataFrame) -> float:
    """Anualiza (base 252) a rentabilidade acumulada com DU do calendário real."""
    from rfquant.comparison import taxa_equivalente

    return taxa_equivalente.rentabilidade_anualizada(df_fundo)


def percentual_cdi(df_fundo: pd.DataFrame, cdi_provider: SGSProvider) -> float:
    """Expressa a rentabilidade anualizada do fundo em % do CDI."""
    from rfquant.comparison import taxa_equivalente

    return taxa_equivalente.percentual_cdi(df_fundo, cdi_provider)
