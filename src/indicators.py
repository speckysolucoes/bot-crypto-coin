"""
Indicadores técnicos — calculados sobre arrays numpy/pandas

Versão 2 — adicionados:
  - Volume relativo (confirma força do movimento)
  - ADX (força da tendência — filtra mercado lateral)
  - Regime de mercado (tendência / lateral)
  - Buy & Hold return (compara estratégia vs segurar)
  - Score de confiança (0-100) para filtrar entradas fracas
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import numpy as np
import pandas as pd


class MarketRegime(Enum):
    TRENDING_UP   = "tendência de alta"
    TRENDING_DOWN = "tendência de baixa"
    RANGING       = "mercado lateral"
    UNKNOWN       = "indefinido"


@dataclass
class Indicators:
    close: float

    # Médias móveis
    ma_fast: Optional[float] = None
    ma_slow: Optional[float] = None

    # RSI
    rsi: Optional[float] = None

    # Bollinger Bands
    bb_upper: Optional[float] = None
    bb_mid:   Optional[float] = None
    bb_lower: Optional[float] = None

    # Volume
    volume_ratio: Optional[float] = None   # volume atual / média — >1.5 = acima da média
    volume_confirm: bool = False            # volume confirma o movimento

    # ADX — força da tendência (>25 = tendência, <20 = lateral)
    adx: Optional[float] = None

    # Regime de mercado
    regime: MarketRegime = MarketRegime.UNKNOWN

    # Buy & Hold do período
    buy_and_hold_pct: Optional[float] = None  # retorno do período vs estratégia

    # Score de confiança do sinal (0-100)
    confidence: int = 0

    # Sinais derivados
    ma_cross_bull:  bool = False
    ma_cross_bear:  bool = False
    rsi_oversold:   bool = False
    rsi_overbought: bool = False
    price_below_bb: bool = False
    price_above_bb: bool = False


# ── Funções de cálculo ────────────────────────────────────────

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_bollinger(series: pd.Series, period: int, std_dev: float):
    mid = sma(series, period)
    std = series.rolling(window=period).std()
    return mid + std_dev * std, mid, mid - std_dev * std


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — mede força da tendência (não direção)."""
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)

    dm_pos = high.diff().clip(lower=0)
    dm_neg = (-low.diff()).clip(lower=0)
    # Quando DM+ < DM- zera e vice-versa
    dm_pos = dm_pos.where(dm_pos > dm_neg, 0)
    dm_neg = dm_neg.where(dm_neg > dm_pos, 0)

    atr    = tr.ewm(span=period, adjust=False).mean()
    di_pos = 100 * dm_pos.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    di_neg = 100 * dm_neg.ewm(span=period, adjust=False).mean() / atr.replace(0, np.nan)
    dx     = 100 * (di_pos - di_neg).abs() / (di_pos + di_neg).replace(0, np.nan)
    return dx.ewm(span=period, adjust=False).mean()


def calc_volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Razão entre volume atual e média — >1.5 indica volume acima da média."""
    vol = df["volume"].astype(float)
    avg = vol.rolling(window=period).mean()
    return vol / avg.replace(0, np.nan)


def detect_regime(adx: float, ma_fast: float, ma_slow: float) -> MarketRegime:
    """
    Classifica o regime de mercado:
      ADX > 25 + MAf > MAs  → tendência de alta
      ADX > 25 + MAf < MAs  → tendência de baixa
      ADX < 20              → mercado lateral
    """
    if adx is None:
        return MarketRegime.UNKNOWN
    if adx > 25:
        return MarketRegime.TRENDING_UP if ma_fast >= ma_slow else MarketRegime.TRENDING_DOWN
    if adx < 20:
        return MarketRegime.RANGING
    return MarketRegime.UNKNOWN


def calc_confidence(ind: "Indicators", cfg) -> int:
    """
    Score de confiança de 0 a 100 para um sinal de COMPRA.
    Combina RSI, volume, ADX e posição nas Bandas de Bollinger.
    """
    score = 0

    # RSI sobrevendido (0-30 pontos)
    if ind.rsi is not None:
        if ind.rsi < cfg.rsi_oversold:
            score += 30
        elif ind.rsi < cfg.rsi_oversold + 10:
            score += 15

    # Cruzamento de MA (0-25 pontos)
    if ind.ma_cross_bull:
        score += 25
    elif ind.ma_fast and ind.ma_slow and ind.ma_fast > ind.ma_slow:
        score += 10

    # Volume confirma (0-20 pontos)
    if ind.volume_confirm:
        score += 20
    elif ind.volume_ratio and ind.volume_ratio > 1.0:
        score += 8

    # Bollinger abaixo (0-15 pontos)
    if ind.price_below_bb:
        score += 15
    elif ind.bb_lower and ind.close < ind.bb_mid:
        score += 5

    # ADX indica tendência (0-10 pontos)
    if ind.adx and ind.adx > 25:
        score += 10

    return min(score, 100)


# ── Função principal ──────────────────────────────────────────

def compute_indicators(df: pd.DataFrame, cfg) -> Optional[Indicators]:
    """
    Recebe DataFrame com colunas open/high/low/close/volume
    e retorna Indicators com todos os valores do último candle.
    """
    min_len = max(cfg.ma_slow, cfg.rsi_period, cfg.bb_period, 28) + 2
    if df is None or len(df) < min_len:
        return None

    close  = df["close"].astype(float)
    has_hlv = {"high", "low", "volume"}.issubset(df.columns)

    ma_f = sma(close, cfg.ma_fast)
    ma_s = sma(close, cfg.ma_slow)
    rsi  = calc_rsi(close, cfg.rsi_period)
    bb_upper, bb_mid, bb_lower = calc_bollinger(close, cfg.bb_period, cfg.bb_std)

    cur      = close.iloc[-1]
    cur_maf  = ma_f.iloc[-1]
    cur_mas  = ma_s.iloc[-1]
    prev_maf = ma_f.iloc[-2]
    prev_mas = ma_s.iloc[-2]

    ind = Indicators(close=float(cur))

    def _f(v): return float(v) if not np.isnan(v) else None

    ind.ma_fast  = _f(cur_maf)
    ind.ma_slow  = _f(cur_mas)
    ind.rsi      = _f(rsi.iloc[-1])
    ind.bb_upper = _f(bb_upper.iloc[-1])
    ind.bb_mid   = _f(bb_mid.iloc[-1])
    ind.bb_lower = _f(bb_lower.iloc[-1])

    # Cruzamentos de MA
    if ind.ma_fast and ind.ma_slow:
        ind.ma_cross_bull = (prev_maf < prev_mas) and (cur_maf >= cur_mas)
        ind.ma_cross_bear = (prev_maf > prev_mas) and (cur_maf <= cur_mas)

    # RSI sinais
    if ind.rsi:
        ind.rsi_oversold   = ind.rsi < cfg.rsi_oversold
        ind.rsi_overbought = ind.rsi > cfg.rsi_overbought

    # Bollinger sinais
    if ind.bb_upper and ind.bb_lower:
        ind.price_below_bb = cur < ind.bb_lower
        ind.price_above_bb = cur > ind.bb_upper

    # Volume (só se coluna disponível)
    if has_hlv:
        vol_ratio = calc_volume_ratio(df, 20)
        ind.volume_ratio   = _f(vol_ratio.iloc[-1])
        # Volume confirma se está acima de 1.3x a média
        ind.volume_confirm = bool(ind.volume_ratio and ind.volume_ratio > 1.3)

        # ADX
        adx_series = calc_adx(df, 14)
        ind.adx = _f(adx_series.iloc[-1])

    # Regime de mercado
    if ind.adx and ind.ma_fast and ind.ma_slow:
        ind.regime = detect_regime(ind.adx, ind.ma_fast, ind.ma_slow)

    # Buy & Hold do período completo
    first_close = float(close.iloc[0])
    if first_close > 0:
        ind.buy_and_hold_pct = round(((cur - first_close) / first_close) * 100, 2)

    # Score de confiança
    ind.confidence = calc_confidence(ind, cfg)

    return ind
