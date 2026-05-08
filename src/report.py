"""
Relatório Semanal
==================
Gera e envia um resumo semanal de performance via Telegram.
Inclui: P&L, win rate, melhor/pior trade, comparação com B&H,
e os parâmetros atuais do bot.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


def load_trades(path: str = "logs/trades.jsonl") -> List[dict]:
    if not Path(path).exists():
        return []
    trades = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                trades.append(json.loads(line.strip()))
            except Exception:
                pass
    return trades


def load_autotune_last(path: str = "logs/autotune_history.jsonl") -> Optional[dict]:
    if not Path(path).exists():
        return None
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                last = json.loads(line.strip())
            except Exception:
                pass
    return last


def generate_weekly_report(cfg, strategy_return_pct: float = 0.0) -> str:
    """
    Gera o texto do relatório semanal.
    """
    trades = load_trades()
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # Filtra trades da última semana
    week_trades = []
    for t in trades:
        try:
            ts = datetime.fromisoformat(t["timestamp"])
            if ts >= week_ago:
                week_trades.append(t)
        except Exception:
            pass

    sells = [t for t in week_trades if t.get("pnl") is not None]
    buys  = [t for t in week_trades if t.get("side") == "BUY"]
    wins  = [t for t in sells if t["pnl"] > 0]

    total_pnl  = sum(t["pnl"] for t in sells)
    win_rate   = (len(wins) / len(sells) * 100) if sells else 0
    best_trade = max(sells, key=lambda t: t["pnl"]) if sells else None
    worst_trade= min(sells, key=lambda t: t["pnl"]) if sells else None

    # Parâmetros atuais
    last_tune = load_autotune_last()
    params_str = ""
    if last_tune and last_tune.get("params"):
        p = last_tune["params"]
        params_str = (
            f"\n⚙️ Parâmetros atuais (auto-tuner):\n"
            f"   MA: {p.get('ma_fast')}/{p.get('ma_slow')} | "
            f"RSI: {p.get('rsi_period')}p\n"
            f"   Stop: {p.get('stop_loss_pct')}% | Take: {p.get('take_profit_pct')}%"
        )

    emoji_pnl = "📈" if total_pnl >= 0 else "📉"

    lines = [
        f"📋 RELATÓRIO SEMANAL — {now.strftime('%d/%m/%Y')}",
        f"Par: {cfg.symbol} | {cfg.timeframe}",
        "─" * 35,
        f"{emoji_pnl} P&L semana:   {'+'if total_pnl>=0 else ''}{total_pnl:.2f} {cfg.quote_currency}",
        f"🎯 Win rate:    {win_rate:.1f}% ({len(wins)}/{len(sells)} trades)",
        f"📊 Total trades: {len(week_trades)} ({len(buys)} compras, {len(sells)} vendas)",
        f"💼 Retorno acum: {'+'if strategy_return_pct>=0 else ''}{strategy_return_pct:.2f}%",
    ]

    if best_trade:
        lines.append(f"✅ Melhor trade: +${best_trade['pnl']:.2f} @ ${best_trade.get('price', 0):,.0f}")
    if worst_trade:
        lines.append(f"❌ Pior trade:   {worst_trade['pnl']:+.2f} @ ${worst_trade.get('price', 0):,.0f}")

    if not sells:
        lines.append("⏳ Nenhum trade fechado esta semana.")

    if params_str:
        lines.append(params_str)

    lines.append("─" * 35)
    lines.append(f"Modo: {'📄 Paper Trading' if cfg.paper_trading else '💰 Live Trading'}")

    return "\n".join(lines)


async def send_weekly_report(cfg, notifier, strategy_return_pct: float = 0.0):
    report = generate_weekly_report(cfg, strategy_return_pct)
    await notifier.send(report)
    return report
