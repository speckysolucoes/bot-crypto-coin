"""
Motor compartilhado de simulação (paper) — backtest e otimizador genético.

Mantém a mesma sequência de sinais/fees que o backtest oficial, para evitar drift
entre `backtest.py` e `src/optimizer.evaluate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.indicators import compute_indicators
from src.strategy import Signal, get_signal

DEFAULT_INITIAL_BALANCE = 10_000.0
FEE_ROUND = 0.999  # ~0.1% por lado, alinhado ao backtest legacy


@dataclass
class PaperState:
    balance: float
    asset: float = 0.0
    buy_price: float = 0.0
    in_position: bool = False


def paper_equity(state: PaperState, mark_price: float) -> float:
    if not state.in_position:
        return state.balance
    return state.balance + state.asset * mark_price


def paper_strategy_return_pct(equity: float, initial_balance: float) -> float:
    return (equity - initial_balance) / initial_balance * 100


def paper_process_candle(
    window: pd.DataFrame,
    cfg: Any,
    state: PaperState,
    *,
    initial_balance: float,
    bar_time: Any = None,
    min_buy_balance: float = 0.0,
) -> Tuple[PaperState, List[Dict[str, Any]]]:
    """
    Um passo por candle: indicadores → get_signal → aplica BUY/SELL simulados.
    `min_buy_balance`: exige saldo cotado estritamente acima deste valor para comprar
    (otimizador usa 10.0 para espelhar comportamento anterior).
    """
    out: List[Dict[str, Any]] = []
    ind = compute_indicators(window, cfg)
    if ind is None:
        return state, out

    eq = paper_equity(state, ind.close)
    sr_pct = paper_strategy_return_pct(eq, initial_balance)
    buy_px = state.buy_price if state.in_position else None
    signal = get_signal(ind, state.in_position, buy_px, cfg, sr_pct)

    if signal in (Signal.BUY, Signal.RANGE_BUY) and not state.in_position:
        if state.balance > min_buy_balance:
            spend = state.balance * (cfg.trade_size_pct / 100)
            qty = (spend * FEE_ROUND) / ind.close
            state.balance -= spend
            state.asset = qty
            state.buy_price = ind.close
            state.in_position = True
            rec: Dict[str, Any] = {"side": "BUY", "price": ind.close}
            if bar_time is not None:
                rec["time"] = bar_time
            out.append(rec)

    elif (
        signal
        in (
            Signal.SELL,
            Signal.STOP_LOSS,
            Signal.TAKE_PROFIT,
            Signal.RANGE_SELL,
        )
        and state.in_position
    ):
        gross = state.asset * ind.close
        net = gross * FEE_ROUND
        pnl = net - (state.asset * state.buy_price)
        state.balance += net
        rec = {
            "side": signal.value,
            "price": ind.close,
            "pnl": pnl,
            "pnl_pct": ((ind.close - state.buy_price) / state.buy_price) * 100,
        }
        if bar_time is not None:
            rec["time"] = bar_time
        out.append(rec)
        state.asset = 0.0
        state.buy_price = 0.0
        state.in_position = False

    return state, out


def paper_finalize_open_position(
    state: PaperState, last_price: float
) -> Tuple[PaperState, List[Dict[str, Any]]]:
    """Fecha posição aberta no último preço (fim da série histórica)."""
    records: List[Dict[str, Any]] = []
    if not state.in_position or state.asset <= 0:
        return state, records
    net = state.asset * last_price * FEE_ROUND
    pnl = net - (state.asset * state.buy_price)
    state.balance += net
    records.append({"side": "SELL (fechamento)", "price": last_price, "pnl": pnl})
    state.asset = 0.0
    state.buy_price = 0.0
    state.in_position = False
    return state, records
