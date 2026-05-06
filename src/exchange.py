"""
Conector de exchange — abstrai ccxt para operações reais e simula para paper trading
"""

import asyncio
from datetime import datetime
from typing import Optional

import ccxt.async_support as ccxt
import pandas as pd


class ExchangeConnector:
    def __init__(self, cfg, logger):
        self.cfg = cfg
        self.logger = logger
        self.exchange: Optional[ccxt.Exchange] = None

        # Estado do paper trading
        self._paper_balance: float = cfg.paper_initial_balance
        self._paper_asset: float = 0.0
        self._paper_buy_price: float = 0.0

    # ── Inicialização ─────────────────────────────────────────

    async def connect(self):
        if self.cfg.paper_trading:
            self.logger.info(
                f"📄 Paper trading ativo — saldo inicial: ${self.cfg.paper_initial_balance:,.2f} USDT"
            )
            return

        exchange_cls = {
            "binance": ccxt.binance,
            "bybit": ccxt.bybit,
            "kucoin": ccxt.kucoin,
        }.get(self.cfg.exchange)

        if not exchange_cls:
            raise ValueError(f"Exchange não suportada: {self.cfg.exchange}")

        params = {
            "apiKey": self.cfg.api_key,
            "secret": self.cfg.api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if self.cfg.api_passphrase:
            params["password"] = self.cfg.api_passphrase

        self.exchange = exchange_cls(params)

        try:
            await self.exchange.load_markets()
            self.logger.info(
                f"✅ Conectado à {self.cfg.exchange.upper()} — {self.cfg.symbol}"
            )
        except Exception as e:
            raise ConnectionError(f"Falha ao conectar na exchange: {e}") from e

    async def close(self):
        if self.exchange:
            await self.exchange.close()

    # ── Dados de mercado ──────────────────────────────────────

    async def fetch_ohlcv(self, limit: int = 100) -> Optional[pd.DataFrame]:
        try:
            if self.cfg.paper_trading:
                raw = await self._fetch_public_ohlcv(limit)
            else:
                raw = await self.exchange.fetch_ohlcv(
                    self.cfg.symbol, self.cfg.timeframe, limit=limit
                )
            if not raw:
                return None
            df = pd.DataFrame(
                raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df.set_index("timestamp")
        except Exception as e:
            self.logger.error(f"Erro ao buscar OHLCV: {e}")
            return None

    async def _fetch_public_ohlcv(self, limit: int):
        """Busca dados públicos (sem API key) para paper trading."""
        tmp_cls = {"binance": ccxt.binance, "bybit": ccxt.bybit, "kucoin": ccxt.kucoin}[
            self.cfg.exchange
        ]
        tmp = tmp_cls({"enableRateLimit": True})
        try:
            data = await tmp.fetch_ohlcv(
                self.cfg.symbol, self.cfg.timeframe, limit=limit
            )
        finally:
            await tmp.close()
        return data

    async def get_ticker_price(self) -> Optional[float]:
        try:
            if self.cfg.paper_trading:
                df = await self.fetch_ohlcv(limit=1)
                return float(df["close"].iloc[-1]) if df is not None else None
            ticker = await self.exchange.fetch_ticker(self.cfg.symbol)
            return float(ticker["last"])
        except Exception as e:
            self.logger.error(f"Erro ao buscar preço: {e}")
            return None

    # ── Ordens ───────────────────────────────────────────────

    async def buy(self, usdt_amount: float) -> Optional[dict]:
        price = await self.get_ticker_price()
        if price is None:
            return None

        if self.cfg.paper_trading:
            return self._paper_buy(usdt_amount, price)

        try:
            qty = self.exchange.amount_to_precision(
                self.cfg.symbol, usdt_amount / price
            )
            order = await self.exchange.create_market_buy_order(
                self.cfg.symbol, float(qty)
            )
            self.logger.info(f"✅ Ordem de compra executada: {order}")
            return {"price": price, "amount": float(qty), "cost": usdt_amount, "order_id": order["id"]}
        except Exception as e:
            self.logger.error(f"Erro ao executar compra: {e}")
            return None

    async def sell(self, asset_amount: float) -> Optional[dict]:
        price = await self.get_ticker_price()
        if price is None:
            return None

        if self.cfg.paper_trading:
            return self._paper_sell(asset_amount, price)

        try:
            qty = self.exchange.amount_to_precision(self.cfg.symbol, asset_amount)
            order = await self.exchange.create_market_sell_order(
                self.cfg.symbol, float(qty)
            )
            self.logger.info(f"✅ Ordem de venda executada: {order}")
            return {"price": price, "amount": asset_amount, "order_id": order["id"]}
        except Exception as e:
            self.logger.error(f"Erro ao executar venda: {e}")
            return None

    # ── Saldo ─────────────────────────────────────────────────

    async def get_balances(self) -> dict:
        if self.cfg.paper_trading:
            return {
                "USDT": self._paper_balance,
                "asset": self._paper_asset,
                "buy_price": self._paper_buy_price,
            }
        try:
            bal = await self.exchange.fetch_balance()
            quote = self.cfg.symbol.split("/")[1]
            base = self.cfg.symbol.split("/")[0]
            return {
                "USDT": float(bal.get(quote, {}).get("free", 0)),
                "asset": float(bal.get(base, {}).get("free", 0)),
                "buy_price": None,
            }
        except Exception as e:
            self.logger.error(f"Erro ao buscar saldo: {e}")
            return {}

    # ── Paper trading interno ─────────────────────────────────

    def _paper_buy(self, usdt_amount: float, price: float) -> dict:
        usdt_amount = min(usdt_amount, self._paper_balance)
        fee = usdt_amount * 0.001  # 0.1% taxa
        net = usdt_amount - fee
        qty = net / price
        self._paper_balance -= usdt_amount
        self._paper_asset += qty
        self._paper_buy_price = price
        return {"price": price, "amount": qty, "cost": usdt_amount, "fee": fee}

    def _paper_sell(self, asset_amount: float, price: float) -> dict:
        gross = asset_amount * price
        fee = gross * 0.001
        net = gross - fee
        self._paper_balance += net
        self._paper_asset -= asset_amount
        result = {
            "price": price,
            "amount": asset_amount,
            "gross": gross,
            "fee": fee,
            "net": net,
            "buy_price": self._paper_buy_price,
        }
        self._paper_buy_price = 0.0
        return result
