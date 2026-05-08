"""
Análise Multi-Timeframe (MTF)
==============================
Verifica a tendência no timeframe maior antes de entrar.
Evita comprar no 1h quando o gráfico de 4h está em queda.

Lógica:
  Timeframe operacional (ex: 1h)  →  gera o sinal de entrada
  Timeframe superior (ex: 4h)     →  filtra: só entra se estiver alinhado

Regras de alinhamento:
  COMPRA  → timeframe superior deve estar em tendência de alta (MAf > MAs)
  VENDA   → timeframe superior deve estar em tendência de baixa (MAf < MAs)
  Se neutro/indefinido → permite a operação (benefício da dúvida)
"""

import asyncio
import logging
from typing import Optional, Tuple
from enum import Enum

import pandas as pd

from src.indicators import compute_indicators, MarketRegime


# Mapeamento: timeframe operacional → timeframe superior de confirmação
HIGHER_TIMEFRAME = {
    "1m":  "15m",
    "3m":  "15m",
    "5m":  "1h",
    "15m": "1h",
    "30m": "4h",
    "1h":  "4h",
    "4h":  "1d",
    "1d":  "1d",   # sem timeframe superior — usa o mesmo
}


class MTFBias(Enum):
    BULLISH  = "alta"      # timeframe maior em tendência de alta
    BEARISH  = "baixa"     # timeframe maior em tendência de baixa
    NEUTRAL  = "neutro"    # indefinido — não filtra
    UNKNOWN  = "sem dados"


class MultiTimeframeAnalyzer:
    def __init__(self, cfg, connector, logger: logging.Logger):
        self.cfg       = cfg
        self.connector = connector
        self.logger    = logger
        self._cache: dict = {}          # cache para não buscar toda hora
        self._cache_time: dict = {}

    def _higher_tf(self) -> str:
        return HIGHER_TIMEFRAME.get(self.cfg.timeframe, "4h")

    async def get_bias(self) -> MTFBias:
        """
        Busca o timeframe superior e retorna o viés (alta/baixa/neutro).
        Usa cache de 1 candle para não fazer requests desnecessários.
        """
        higher_tf = self._higher_tf()

        # Mesmo timeframe = sem confirmação superior, permite tudo
        if higher_tf == self.cfg.timeframe:
            return MTFBias.NEUTRAL

        # Cache: só rebusca se passou tempo de 1 candle do TF superior
        cache_ttl = self._tf_seconds(higher_tf)
        import time
        now = time.time()
        last = self._cache_time.get(higher_tf, 0)
        if now - last < cache_ttl and higher_tf in self._cache:
            return self._cache[higher_tf]

        original_tf = self.cfg.timeframe
        try:
            self.cfg.timeframe = higher_tf
            df = await self.connector.fetch_ohlcv(limit=60)
        except Exception as e:
            self.logger.warning(f"MTF: erro ao buscar {higher_tf}: {e}")
            return MTFBias.UNKNOWN
        finally:
            self.cfg.timeframe = original_tf

        if df is None or len(df) < 30:
            return MTFBias.UNKNOWN

        ind = compute_indicators(df, self.cfg)
        if ind is None:
            return MTFBias.UNKNOWN

        # Determina viés pelo regime e direção das médias
        if ind.regime == MarketRegime.TRENDING_UP:
            bias = MTFBias.BULLISH
        elif ind.regime == MarketRegime.TRENDING_DOWN:
            bias = MTFBias.BEARISH
        elif ind.ma_fast and ind.ma_slow:
            bias = MTFBias.BULLISH if ind.ma_fast > ind.ma_slow else MTFBias.BEARISH
        else:
            bias = MTFBias.NEUTRAL

        self._cache[higher_tf] = bias
        self._cache_time[higher_tf] = now

        rsi_s = f"{ind.rsi:.1f}" if ind.rsi is not None else "?"
        adx_s = f"{ind.adx:.1f}" if ind.adx is not None else "?"
        self.logger.info(
            f"🔭 MTF [{higher_tf}]: viés={bias.value} | "
            f"RSI={rsi_s} | "
            f"ADX={adx_s} | "
            f"Regime={ind.regime.value}"
        )
        return bias

    def allows_buy(self, bias: MTFBias) -> bool:
        """Retorna True se o viés do TF superior permite compra."""
        return bias in (MTFBias.BULLISH, MTFBias.NEUTRAL, MTFBias.UNKNOWN)

    def allows_sell(self, bias: MTFBias) -> bool:
        """Retorna True se o viés do TF superior permite venda/saída."""
        return True  # saída sempre permitida independente do TF superior

    def _tf_seconds(self, tf: str) -> int:
        mapping = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
        }
        return mapping.get(tf, 3600)
