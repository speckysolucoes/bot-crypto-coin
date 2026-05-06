"""
TradingBot v4 — loop principal com todas as melhorias integradas

  1. Trailing Stop Loss        — stop sobe com o preço, trava lucro
  2. Reconexão automática      — backoff exponencial em quedas de conexão
  3. Multi-timeframe           — confirma tendência no TF superior antes de entrar
  4. Position sizing dinâmico  — investe mais quando confiança é alta
  5. Relatório semanal         — resumo automático toda segunda-feira
"""

import asyncio
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from src.config import Config
from src.exchange import ExchangeConnector
from src.indicators import compute_indicators
from src.strategy import Signal, get_signal, signal_description
from src.notifier import Notifier
from src.trailing_stop import TrailingStop
from src.reconnect import ReconnectionManager
from src.mtf import MultiTimeframeAnalyzer, MTFBias
from src.position_sizing import PositionSizer
from src.report import send_weekly_report
from scheduler import WeeklyScheduler

TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900,
    "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
}


class TradingBot:
    def __init__(self, cfg: Config, logger):
        self.cfg       = cfg
        self.logger    = logger
        self.connector = ExchangeConnector(cfg, logger)
        self.notifier  = Notifier(cfg, logger)

        # Estado
        self.in_position:      bool  = False
        self.buy_price:        Optional[float] = None
        self.position_size:    float = 0.0
        self.entry_confidence: int   = 0
        self.trailing_stop:    Optional[TrailingStop] = None

        # Métricas
        self.trades_today:      int   = 0
        self.pnl_today:         float = 0.0
        self.total_trades:      int   = 0
        self.winning_trades:    int   = 0
        self.total_pnl:         float = 0.0
        self.day_start_balance: float = 0.0
        self.current_day:       date  = date.today()
        self._last_report:      Optional[date] = None

        # Módulos
        self.reconnect = ReconnectionManager(logger)
        self.mtf       = MultiTimeframeAnalyzer(cfg, self.connector, logger)
        self.sizer     = PositionSizer(base_pct=cfg.trade_size_pct)
        self.scheduler = WeeklyScheduler(
            cfg=cfg, logger=logger,
            interval_days=7, run_hour=3,
            train_days=60, val_days=14,
            population=40, generations=25,
            min_val_return=0.0, restart_bot_after=True,
        )
        self.running = False

    # ── Ciclo principal ───────────────────────────────────────

    async def run(self):
        await self.connector.connect()
        await self.notifier.send(
            f"🤖 Bot v4 iniciado\n"
            f"Par: {self.cfg.symbol} | {self.cfg.timeframe}\n"
            f"Trailing stop ✅ | MTF ✅ | Sizing dinâmico ✅"
        )
        bal = await self.connector.get_balances()
        self.day_start_balance = bal.get("USDT", self.cfg.paper_initial_balance)

        self.running   = True
        sleep_secs     = TIMEFRAME_SECONDS.get(self.cfg.timeframe, 900)
        self.logger.info(f"⏱  Loop a cada {sleep_secs}s | Par: {self.cfg.symbol}")

        while self.running:
            try:
                await self.scheduler.maybe_run(bot=self)
                await self._maybe_send_weekly_report()
                await self._tick()
            except Exception as e:
                self.logger.error(f"Erro no tick: {e}", exc_info=True)
                await asyncio.sleep(30)

            self.logger.info(f"💤 Aguardando {sleep_secs}s até próxima vela...")
            await asyncio.sleep(sleep_secs)

    # ── Tick ─────────────────────────────────────────────────

    async def _tick(self):
        self._check_day_reset()

        # 1. Candles com retry automático
        df = await self.reconnect.execute(
            self.connector.fetch_ohlcv, limit=150, label="fetch_ohlcv"
        )
        if df is None:
            self.logger.warning("Sem dados de mercado — pulando tick.")
            return

        # 2. Indicadores
        ind = compute_indicators(df, self.cfg)
        if ind is None:
            self.logger.warning("Indicadores insuficientes — aguardando mais candles.")
            return

        price = ind.close
        self._log_indicators(price, ind)

        # 3. Trailing stop (verifica antes de qualquer outra coisa)
        if self.in_position and self.trailing_stop:
            if self.trailing_stop.update(price):
                self.logger.info(f"🔔 Trailing stop acionado! {self.trailing_stop.summary()}")
                await self._execute_sell(price, Signal.STOP_LOSS, reason="trailing stop")
                return
            self.logger.info(f"📍 {self.trailing_stop.summary()}")

        # 4. Limite de perda diária
        if self._daily_loss_breached():
            self.logger.warning("🚨 Limite de perda diária atingido!")
            await self.notifier.send("🚨 PERDA DIÁRIA MÁXIMA ATINGIDA — bot pausado até meia-noite.")
            await asyncio.sleep(self._seconds_until_midnight())
            return

        # 5. Retorno acumulado vs B&H
        bal = await self.connector.get_balances()
        usdt_free = bal.get("USDT", 0)
        current_total = usdt_free + (self.position_size * price if self.in_position else 0)
        strategy_return_pct = (
            (current_total - self.cfg.paper_initial_balance)
            / self.cfg.paper_initial_balance * 100
        )
        self.logger.info(
            f"🧠 Regime: {ind.regime.value} | Confiança: {ind.confidence}/100 | "
            f"ADX: {ind.adx:.1f if ind.adx else 'N/A'} | "
            f"Vol: {ind.volume_ratio:.2f if ind.volume_ratio else 'N/A'}x | "
            f"B&H: {ind.buy_and_hold_pct:+.1f}% | Bot: {strategy_return_pct:+.1f}%"
        )

        # 6. Multi-timeframe (só para entradas novas)
        mtf_bias = MTFBias.NEUTRAL
        if not self.in_position:
            mtf_bias = await self.mtf.get_bias()

        # 7. Sinal
        signal = get_signal(ind, self.in_position, self.buy_price, self.cfg, strategy_return_pct)
        self.logger.info(f"📊 {signal_description(signal, ind)}")

        # 8. Filtro MTF — bloqueia compra se TF superior estiver em baixa
        if signal in (Signal.BUY, Signal.RANGE_BUY):
            if not self.mtf.allows_buy(mtf_bias):
                self.logger.info(f"🚫 Compra bloqueada pelo MTF — viés: {mtf_bias.value}")
                return

        # 9. Executa
        if signal in (Signal.BUY, Signal.RANGE_BUY):
            await self._execute_buy(price, ind.confidence)
        elif signal in (Signal.SELL, Signal.STOP_LOSS, Signal.TAKE_PROFIT, Signal.RANGE_SELL):
            await self._execute_sell(price, signal)

    # ── Ordens ───────────────────────────────────────────────

    async def _execute_buy(self, price: float, confidence: int = 60):
        bal  = await self.connector.get_balances()
        usdt = bal.get("USDT", 0)
        spend = self.sizer.usdt_amount(usdt, confidence)

        if spend < 10:
            self.logger.warning(f"Ordem muito pequena ou saldo insuficiente (${spend:.2f}).")
            return

        self.logger.info(f"💡 {self.sizer.explain(confidence)} → ${spend:.2f} USDT")

        result = await self.reconnect.execute(
            self.connector.buy, spend, label="ordem de compra"
        )
        if not result:
            return

        self.in_position      = True
        self.buy_price        = result["price"]
        self.position_size    = result["amount"]
        self.entry_confidence = confidence
        self.total_trades    += 1

        self.trailing_stop = TrailingStop(
            buy_price=price,
            trail_pct=self.cfg.stop_loss_pct,
            activate_pct=1.0,
        )

        msg = (
            f"🟢 COMPRA — {self.cfg.symbol}\n"
            f"   Preço:      ${price:,.2f}\n"
            f"   Qtd:        {result['amount']:.6f}\n"
            f"   Valor:      ${result['cost']:.2f} USDT\n"
            f"   Confiança:  {confidence}/100\n"
            f"   Stop trail: ${price*(1-self.cfg.stop_loss_pct/100):,.2f}\n"
            f"   Take profit:${price*(1+self.cfg.take_profit_pct/100):,.2f}"
        )
        self.logger.info(msg)
        await self.notifier.send(msg)
        self._save_trade("BUY", result, confidence=confidence)

    async def _execute_sell(self, price: float, signal: Signal, reason: str = ""):
        if not self.in_position or self.position_size <= 0:
            return

        result = await self.reconnect.execute(
            self.connector.sell, self.position_size, label="ordem de venda"
        )
        if not result:
            return

        pnl     = (price - self.buy_price) * self.position_size
        pnl_pct = ((price - self.buy_price) / self.buy_price) * 100
        self.pnl_today += pnl
        self.total_pnl += pnl
        if pnl > 0:
            self.winning_trades += 1

        emoji      = "💰" if signal == Signal.TAKE_PROFIT else ("🔴" if pnl < 0 else "🟡")
        reason_str = f" ({reason})" if reason else ""
        peak_str   = f"\n   Pico atingido: ${self.trailing_stop.highest_price:,.2f}" if self.trailing_stop else ""

        msg = (
            f"{emoji} VENDA{reason_str} [{signal.value}]\n"
            f"   Par:     {self.cfg.symbol}\n"
            f"   Entrada: ${self.buy_price:,.2f} | Saída: ${price:,.2f}\n"
            f"   P&L:     {pnl:+.2f} USDT ({pnl_pct:+.2f}%){peak_str}\n"
            f"   Win rate: {self._win_rate()}% | P&L total: {self.total_pnl:+.2f} USDT"
        )
        self.logger.info(msg)
        await self.notifier.send(msg)
        self._save_trade("SELL", result, pnl=pnl, signal=signal.value)

        self.in_position      = False
        self.buy_price        = None
        self.position_size    = 0.0
        self.entry_confidence = 0
        self.trailing_stop    = None

    # ── Relatório semanal ─────────────────────────────────────

    async def _maybe_send_weekly_report(self):
        today = date.today()
        if today.weekday() == 0 and today != self._last_report:
            self._last_report = today
            bal = await self.connector.get_balances()
            total = bal.get("USDT", 0) + (self.position_size * (self.buy_price or 0))
            ret   = ((total - self.cfg.paper_initial_balance) / self.cfg.paper_initial_balance) * 100
            report = await send_weekly_report(self.cfg, self.notifier, ret)
            self.logger.info(f"📋 Relatório semanal:\n{report}")

    # ── Utilitários ───────────────────────────────────────────

    def _log_indicators(self, price: float, ind):
        self.logger.info(
            f"📈 {self.cfg.symbol} ${price:,.2f} | "
            f"RSI={ind.rsi:.1f if ind.rsi else 'N/A'} | "
            f"MAf={ind.ma_fast:.2f if ind.ma_fast else 'N/A'} | "
            f"MAs={ind.ma_slow:.2f if ind.ma_slow else 'N/A'} | "
            f"Posição={'SIM' if self.in_position else 'NÃO'}"
        )

    def _daily_loss_breached(self) -> bool:
        if not self.day_start_balance:
            return False
        return (self.pnl_today / self.day_start_balance * 100) <= -self.cfg.max_daily_loss_pct

    def _check_day_reset(self):
        today = date.today()
        if today != self.current_day:
            self.logger.info("🌅 Novo dia — resetando contadores diários.")
            self.trades_today = 0
            self.pnl_today    = 0.0
            self.current_day  = today

    def _win_rate(self) -> int:
        if self.total_trades == 0:
            return 0
        return int((self.winning_trades / self.total_trades) * 100)

    def _seconds_until_midnight(self) -> int:
        midnight = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
        return int((midnight - datetime.now()).total_seconds())

    def _save_trade(self, side: str, result: dict, pnl: float = None,
                    signal: str = None, confidence: int = None):
        Path("logs").mkdir(exist_ok=True)
        record = {
            "timestamp":  datetime.utcnow().isoformat(),
            "symbol":     self.cfg.symbol,
            "side":       side,
            "price":      result.get("price"),
            "amount":     result.get("amount"),
            "pnl":        pnl,
            "signal":     signal,
            "confidence": confidence,
            "paper":      self.cfg.paper_trading,
        }
        with open("logs/trades.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")

    async def shutdown(self):
        self.running = False
        bal = await self.connector.get_balances()
        summary = (
            f"⏹  Bot encerrado\n"
            f"   Trades: {self.total_trades} | Win rate: {self._win_rate()}%\n"
            f"   P&L total: {self.total_pnl:+.2f} USDT\n"
            f"   P&L hoje:  {self.pnl_today:+.2f} USDT\n"
            f"   Saldo USDT: {bal.get('USDT', 0):.2f}"
        )
        self.logger.info(summary)
        await self.notifier.send(summary)
        await self.connector.close()
