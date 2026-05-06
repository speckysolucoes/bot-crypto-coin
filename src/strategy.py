"""
Estratégia adaptativa v2
=========================
Resolve três problemas da v1:

  PROBLEMA 1 — Win rate baixo (47%)
  SOLUÇÃO    → Exige score de confiança mínimo (padrão 60/100) antes de entrar.
               O score combina RSI + volume + ADX + BB. Entradas fracas são ignoradas.

  PROBLEMA 2 — Poucos trades (17 em 90 dias)
  SOLUÇÃO    → Modo RANGING: quando o mercado está lateral (ADX < 20),
               o bot usa Bandas de Bollinger como suporte/resistência para
               operar mais vezes dentro do range.

  PROBLEMA 3 — Underperform vs Buy & Hold
  SOLUÇÃO    → Se o Buy & Hold do período estiver superando a estratégia
               em mais de BUY_AND_HOLD_THRESHOLD%, o bot para de operar
               e aguarda — melhor não fazer nada do que perder para o mercado.
"""

from enum import Enum
from typing import Optional

from src.indicators import Indicators, MarketRegime

# Limiar de confiança mínimo para entrar numa operação (0-100)
MIN_CONFIDENCE = 55

# Se Buy&Hold superar a estratégia por mais que X%, o bot pausa as entradas
BUY_AND_HOLD_THRESHOLD = 15.0


class Signal(Enum):
    BUY          = "COMPRAR"
    SELL         = "VENDER"
    HOLD         = "AGUARDAR"
    STOP_LOSS    = "STOP LOSS"
    TAKE_PROFIT  = "TAKE PROFIT"
    PAUSED_BNH   = "PAUSADO (buy&hold superior)"
    RANGE_BUY    = "COMPRAR (range)"
    RANGE_SELL   = "VENDER (range)"


def get_signal(
    ind: Indicators,
    in_position: bool,
    buy_price: Optional[float],
    cfg,
    strategy_return_pct: float = 0.0,   # retorno acumulado da estratégia até agora
) -> Signal:
    """
    Avalia os indicadores e retorna o sinal de ação.

    Parâmetros extras:
      strategy_return_pct: retorno acumulado da estratégia (para comparar com B&H)
    """

    # ── Proteção Buy & Hold ───────────────────────────────────
    # Se o mercado subiu muito mais do que a estratégia, pausa entradas novas.
    # (Não fecha posição aberta — só bloqueia novas entradas.)
    if not in_position and ind.buy_and_hold_pct is not None:
        bnh_advantage = ind.buy_and_hold_pct - strategy_return_pct
        if bnh_advantage > BUY_AND_HOLD_THRESHOLD:
            return Signal.PAUSED_BNH

    # ── Gestão de posição aberta ──────────────────────────────
    if in_position and buy_price is not None:
        change_pct = ((ind.close - buy_price) / buy_price) * 100

        if change_pct <= -cfg.stop_loss_pct:
            return Signal.STOP_LOSS

        if change_pct >= cfg.take_profit_pct:
            return Signal.TAKE_PROFIT

        # Saída em tendência: cruzamento baixista + RSI sobrecomprado
        if ind.regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN):
            if ind.ma_cross_bear and ind.rsi_overbought:
                return Signal.SELL

        # Saída em range: preço voltou para a banda superior
        if ind.regime == MarketRegime.RANGING:
            if ind.price_above_bb or ind.rsi_overbought:
                return Signal.RANGE_SELL

        return Signal.HOLD

    # ── Sem posição — procura entrada ─────────────────────────
    if not in_position:

        # ── Modo TENDÊNCIA (ADX > 25) ─────────────────────────
        if ind.regime in (MarketRegime.TRENDING_UP, MarketRegime.UNKNOWN):

            # Condição principal: cruzamento altista + RSI sobrevendido
            buy_trend = (ind.ma_cross_bull and ind.rsi_oversold)

            # Condição extra: BB inferior + RSI sobrevendido
            buy_bb = (ind.price_below_bb and ind.rsi_oversold)

            if (buy_trend or buy_bb) and ind.confidence >= MIN_CONFIDENCE:
                return Signal.BUY

        # ── Modo LATERAL (ADX < 20) ───────────────────────────
        # Opera mais vezes usando suporte/resistência das Bandas de Bollinger
        if ind.regime == MarketRegime.RANGING:

            # Compra na banda inferior com RSI sobrevendido
            range_buy = (
                ind.price_below_bb
                and ind.rsi_oversold
                and ind.confidence >= MIN_CONFIDENCE - 10   # critério levemente relaxado
            )

            if range_buy:
                return Signal.RANGE_BUY

    return Signal.HOLD


def signal_description(signal: Signal, ind: Indicators) -> str:
    """Texto explicativo do sinal para o log."""
    regime = ind.regime.value if ind.regime else "?"
    conf   = ind.confidence
    bnh    = f"{ind.buy_and_hold_pct:+.1f}%" if ind.buy_and_hold_pct is not None else "?"
    adx    = f"{ind.adx:.1f}" if ind.adx else "?"
    vol    = f"{ind.volume_ratio:.2f}x" if ind.volume_ratio else "?"

    base = f"[regime={regime} | confiança={conf}/100 | ADX={adx} | vol={vol} | B&H={bnh}]"

    descriptions = {
        Signal.BUY:         f"✅ COMPRAR — {base}",
        Signal.RANGE_BUY:   f"✅ COMPRAR (range) — {base}",
        Signal.SELL:        f"⬇️  VENDER — {base}",
        Signal.RANGE_SELL:  f"⬇️  VENDER (range) — {base}",
        Signal.STOP_LOSS:   f"🛑 STOP LOSS acionado",
        Signal.TAKE_PROFIT: f"💰 TAKE PROFIT atingido",
        Signal.PAUSED_BNH:  f"⏸️  PAUSADO — Buy&Hold superando estratégia em {(ind.buy_and_hold_pct or 0):.1f}%",
        Signal.HOLD:        f"⏳ AGUARDAR — {base}",
    }
    return descriptions.get(signal, signal.value)
