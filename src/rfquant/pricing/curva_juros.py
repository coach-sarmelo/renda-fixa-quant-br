"""Interpolação da Estrutura a Termo da Taxa de Juros (ETTJ).

Implementa três métodos:
    - Flat-forward (padrão B3/ANBIMA — forward constante entre vértices).
    - Interpolação linear por prazo (simples, robusta).
    - Nelson-Siegel (paramétrica, suave, padrão acadêmico).

Uso típico:
    >>> pontos = [(1.0, 0.115), (2.0, 0.118), (5.0, 0.125), (10.0, 0.135)]
    >>> e = ETTJ(pontos, metodo="flat_forward")
    >>> e.taxa(3.5)  # taxa interpolada para 3,5 anos
    0.1230...
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit

Metodo = Literal["linear", "flat_forward", "nelson_siegel"]


@dataclass
class ETTJ:
    """Estrutura a Termo da Taxa de Juros.

    Attributes:
        pontos: Lista de tuplas (prazo_em_anos, taxa_anual).
        metodo: "flat_forward" (padrão B3), "linear" ou "nelson_siegel".
    """

    pontos: list[tuple[float, float]]
    metodo: Metodo = "flat_forward"

    def __post_init__(self) -> None:
        if len(self.pontos) < 2:
            raise ValueError("ETTJ precisa de pelo menos 2 pontos.")
        prazos = [p for p, _ in self.pontos]
        if any(p <= 0 for p in prazos):
            raise ValueError("Prazos devem ser positivos.")
        if any(p2 <= p1 for p1, p2 in pairwise(prazos)):
            raise ValueError("Pontos devem ter prazos estritamente crescentes.")
        # Mesmo domínio do núcleo de PU (pu._pu_de_fluxos): taxa <= -100%
        # torna o fator de capitalização nulo/negativo — o flat-forward
        # (método default) dividiria por zero na interpolação.
        if any(t <= -1 for _, t in self.pontos):
            raise ValueError("Taxa anual deve ser maior que -100%.")
        self._prazos = np.array([p for p, _ in self.pontos], dtype=float)
        self._taxas = np.array([t for _, t in self.pontos], dtype=float)
        self._params: tuple[float, ...] | None = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def taxa(self, prazo: float) -> float:
        """Retorna a taxa anual interpolada para um prazo em anos."""
        if prazo <= 0:
            raise ValueError("Prazo deve ser positivo.")
        if self.metodo == "linear":
            return float(np.interp(prazo, self._prazos, self._taxas))
        if self.metodo == "flat_forward":
            return self._flat_forward(prazo)
        return self._nelson_siegel(prazo)

    def taxa_vetor(self, prazos: np.ndarray | list[float]) -> np.ndarray:
        """Retorna array de taxas para um vetor de prazos."""
        return np.array([self.taxa(float(p)) for p in prazos])

    def _flat_forward(self, prazo: float) -> float:
        """Interpolação flat-forward (padrão B3/ANBIMA).

        Forward constante entre vértices: o fator de desconto é log-linear
        entre nós consecutivos. Equivalente a:

            (1 + r(t))^t = (1 + r₁)^t₁ × [(1 + r₂)^t₂ / (1 + r₁)^t₁]^((t - t₁)/(t₂ - t₁))

        Para prazo fora do intervalo dos nós, usa a taxa do nó mais próximo
        (extrapolação flat, sem arbitragem).
        """
        if prazo <= self._prazos[0]:
            return float(self._taxas[0])
        if prazo >= self._prazos[-1]:
            return float(self._taxas[-1])
        idx = int(np.searchsorted(self._prazos, prazo)) - 1
        t1, t2 = float(self._prazos[idx]), float(self._prazos[idx + 1])
        r1, r2 = float(self._taxas[idx]), float(self._taxas[idx + 1])
        fator1 = (1 + r1) ** t1
        fator2 = (1 + r2) ** t2
        alpha = (prazo - t1) / (t2 - t1)
        fator = fator1 * (fator2 / fator1) ** alpha
        return float(fator ** (1 / prazo) - 1)

    def fator_desconto(self, prazo: float) -> float:
        """Fator de desconto (1 + y)^(-prazo)."""
        return float((1 + self.taxa(prazo)) ** (-prazo))

    # ------------------------------------------------------------------
    # Nelson-Siegel
    # ------------------------------------------------------------------
    @staticmethod
    def _ns_func(
        t: np.ndarray,
        beta0: float,
        beta1: float,
        beta2: float,
        tau: float,
    ) -> np.ndarray:
        """Modelo de Nelson-Siegel.

        y(t) = β0 + β1 · [(1 - e^(-t/τ)) / (t/τ)]
                  + β2 · [(1 - e^(-t/τ)) / (t/τ) - e^(-t/τ)]
        """
        x = np.where(t == 0, 1e-6, t) / tau
        fator1 = (1 - np.exp(-x)) / x
        fator2 = fator1 - np.exp(-x)
        return beta0 + beta1 * fator1 + beta2 * fator2

    def _fit_nelson_siegel(self) -> tuple[float, float, float, float]:
        if self._params is not None:
            return self._params  # type: ignore[return-value]

        # Chutes iniciais razoáveis para o Brasil
        p0 = [
            float(self._taxas[-1]),  # β0 ≈ taxa longa
            float(self._taxas[0] - self._taxas[-1]),  # β1 ≈ inclinação
            -0.01,  # β2
            2.0,  # τ
        ]
        bounds = (
            [0.0, -0.5, -0.5, 0.1],
            [1.0, 0.5, 0.5, 30.0],
        )
        try:
            # Com poucos vértices os parâmetros do NS são pouco identificados
            # (Jacobiano quase degenerado) e o curve_fit avisa que a matriz de
            # covariância não é estimável — o ajuste em si segue válido (os nós
            # são reproduzidos a 1e-3 no teste do método). O aviso seria ruído
            # para todo consumidor da opção, então é silenciado aqui, só no fit.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                params, _ = curve_fit(
                    self._ns_func,
                    self._prazos,
                    self._taxas,
                    p0=p0,
                    bounds=bounds,
                    maxfev=10_000,
                )
            self._params = tuple(float(p) for p in params)
        except Exception:
            # Fallback: curva flat na última taxa (β1 = β2 = 0) se o fit falhar
            self._params = (float(self._taxas[-1]), 0.0, 0.0, 2.0)
        return self._params  # type: ignore[return-value]

    def _nelson_siegel(self, prazo: float) -> float:
        b0, b1, b2, tau = self._fit_nelson_siegel()
        return float(self._ns_func(np.array([prazo]), b0, b1, b2, tau)[0])


# ----------------------------------------------------------------------
# Utilitários de conversão de taxas
# ----------------------------------------------------------------------
def taxa_efetiva_para_nominal(taxa_efetiva: float, periodos: int = 2) -> float:
    """Converte taxa efetiva anual para nominal (base `periodos` por ano).

    Exemplo: 10% efetivo a.a. → nominal semestral capitalizado.
    """
    if periodos <= 0:
        raise ValueError("Períodos deve ser positivo.")
    if taxa_efetiva <= -1:
        raise ValueError("Taxa efetiva deve ser maior que -100%.")
    return float(periodos * ((1 + taxa_efetiva) ** (1 / periodos) - 1))


def taxa_nominal_para_efetiva(taxa_nominal: float, periodos: int = 2) -> float:
    """Converte taxa nominal para efetiva anual."""
    if periodos <= 0:
        raise ValueError("Períodos deve ser positivo.")
    return (1 + taxa_nominal / periodos) ** periodos - 1


def taxa_pre_para_pos(pre: float, ipca_esperado: float) -> float:
    """Converte taxa prefixada em taxa real (IPCA+) equivalente.

    Relação de Fisher exata:
        (1 + pre) = (1 + real) × (1 + ipca)
    """
    if ipca_esperado <= -1:
        raise ValueError("IPCA esperado deve ser maior que -100%.")
    return (1 + pre) / (1 + ipca_esperado) - 1


def taxa_pos_para_pre(real: float, ipca_esperado: float) -> float:
    """Converte taxa real (IPCA+) em prefixada equivalente."""
    if ipca_esperado <= -1:
        raise ValueError("IPCA esperado deve ser maior que -100%.")
    return (1 + real) * (1 + ipca_esperado) - 1
