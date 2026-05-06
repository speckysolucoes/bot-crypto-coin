"""
Backtesting — testa a estratégia em dados históricos antes de usar ao vivo

Uso:
    python backtest.py --symbol BTC/USDT --timeframe 1h --days 90
"""

import argparse
import asyncio
import json
from datetime import datetime, timedelta

import ccxt.async_support as ccxt
import pandas as pd
import numpy as np

from src.config import load_config
from src.indicators import compute_indicators
from src.strategy import Signal, get_signal


async def fetch_history(symbol: str, timeframe: str, days: int, exchange_id: str = "binance") -> pd.DataFrame:
    cls = getattr(ccxt, exchange_id)
    ex = cls({"enableRateLimit": True})
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
    all_candles = []
    try:
        while True:
            batch = await ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not batch:
                break
            all_candles.extend(batch)
            since = batch[-1][0] + 1
            if len(batch) < 1000:
                break
            await asyncio.sleep(0.5)
    finally:
        await ex.close()

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df.set_index("timestamp")


def run_backtest(df: pd.DataFrame, cfg) -> dict:
    balance = 10_000.0
    asset = 0.0
    buy_price = 0.0
    in_position = False
    trades = []

    for i in range(len(df)):
        window = df.iloc[: i + 1]
        ind = compute_indicators(window, cfg)
        if ind is None:
            continue

        signal = get_signal(ind, in_position, buy_price if in_position else None, cfg)

        if signal == Signal.BUY and not in_position:
            spend = balance * (cfg.trade_size_pct / 100)
            qty = (spend * 0.999) / ind.close  # 0.1% taxa
            balance -= spend
            asset = qty
            buy_price = ind.close
            in_position = True
            trades.append({"side": "BUY", "price": ind.close, "time": window.index[-1]})

        elif signal in (Signal.SELL, Signal.STOP_LOSS, Signal.TAKE_PROFIT) and in_position:
            gross = asset * ind.close
            net = gross * 0.999
            pnl = net - (asset * buy_price)
            balance += net
            trades.append({
                "side": signal.value,
                "price": ind.close,
                "time": window.index[-1],
                "pnl": pnl,
                "pnl_pct": ((ind.close - buy_price) / buy_price) * 100,
            })
            asset = 0.0
            in_position = False

    # Se encerrou com posição aberta, fecha no último preço
    if in_position and asset > 0:
        last_price = float(df["close"].iloc[-1])
        net = asset * last_price * 0.999
        pnl = net - (asset * buy_price)
        balance += net
        trades.append({"side": "SELL (fechamento)", "price": last_price, "pnl": pnl})

    sells = [t for t in trades if "pnl" in t]
    wins = [t for t in sells if t["pnl"] > 0]
    total_pnl = sum(t["pnl"] for t in sells)
    final_balance = balance

    return {
        "initial_balance": 10_000.0,
        "final_balance": round(final_balance, 2),
        "total_return_pct": round(((final_balance - 10_000) / 10_000) * 100, 2),
        "total_pnl": round(total_pnl, 2),
        "total_trades": len(sells),
        "winning_trades": len(wins),
        "win_rate_pct": round(len(wins) / len(sells) * 100, 1) if sells else 0,
        "avg_pnl_pct": round(np.mean([t["pnl_pct"] for t in sells if "pnl_pct" in t]), 2) if sells else 0,
        "trades": trades[-20:],  # últimos 20
    }


async def main():
    parser = argparse.ArgumentParser(description="CryptoBot Backtester")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--exchange", default="binance")
    args = parser.parse_args()

    # Carrega config padrão (paper trading)
    import os
    os.environ.setdefault("PAPER_TRADING", "true")
    os.environ.setdefault("SYMBOL", args.symbol)
    os.environ.setdefault("TIMEFRAME", args.timeframe)
    from dotenv import load_dotenv
    load_dotenv(".env", override=False)
    cfg = load_config()
    cfg.symbol = args.symbol
    cfg.timeframe = args.timeframe

    print(f"\n🔍 Buscando {args.days} dias de {args.symbol} [{args.timeframe}] na {args.exchange}...")
    df = await fetch_history(args.symbol, args.timeframe, args.days, args.exchange)
    print(f"   {len(df)} candles carregados ({df.index[0].date()} → {df.index[-1].date()})")

    print("\n⚙️  Executando backtest...")
    result = run_backtest(df, cfg)

    print("\n" + "=" * 50)
    print("  RESULTADO DO BACKTEST")
    print("=" * 50)
    print(f"  Período:        {args.days} dias | {args.timeframe}")
    print(f"  Par:            {args.symbol}")
    print(f"  Saldo inicial:  ${result['initial_balance']:,.2f}")
    print(f"  Saldo final:    ${result['final_balance']:,.2f}")
    print(f"  Retorno total:  {result['total_return_pct']:+.2f}%")
    print(f"  P&L total:      ${result['total_pnl']:+,.2f}")
    print(f"  Trades:         {result['total_trades']}")
    print(f"  Win rate:       {result['win_rate_pct']}%")
    print(f"  P&L médio/trade: {result['avg_pnl_pct']:+.2f}%")
    print("=" * 50)

    # Salva resultado
    with open("logs/backtest_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print("\n💾 Resultado salvo em logs/backtest_result.json")


if __name__ == "__main__":
    asyncio.run(main())
