"""
Carregamento e validação de configurações do .env
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv


@dataclass
class Config:
    # Exchange
    exchange: str = "binance"
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: Optional[str] = None

    # Par / Timeframe
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"

    # Modo
    paper_trading: bool = True
    paper_initial_balance: float = 10_000.0

    # Estratégia
    ma_fast: int = 7
    ma_slow: int = 21
    rsi_period: int = 14
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    bb_period: int = 20
    bb_std: float = 2.0

    # Gestão de risco
    trade_size_pct: float = 20.0
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    max_open_trades: int = 1
    max_daily_loss_pct: float = 10.0

    # Telegram
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Logs
    log_level: str = "INFO"
    log_file: str = "logs/bot.log"


def _bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes", "sim")


def load_config(env_file: str = ".env") -> Config:
    load_dotenv(env_file, override=True)

    cfg = Config(
        exchange=os.getenv("EXCHANGE", "binance").lower(),
        api_key=os.getenv("API_KEY", ""),
        api_secret=os.getenv("API_SECRET", ""),
        api_passphrase=os.getenv("API_PASSPHRASE"),

        symbol=os.getenv("SYMBOL", "BTC/USDT"),
        timeframe=os.getenv("TIMEFRAME", "15m"),

        paper_trading=_bool(os.getenv("PAPER_TRADING", "true")),
        paper_initial_balance=float(os.getenv("PAPER_INITIAL_BALANCE", "10000")),

        ma_fast=int(os.getenv("MA_FAST", "7")),
        ma_slow=int(os.getenv("MA_SLOW", "21")),
        rsi_period=int(os.getenv("RSI_PERIOD", "14")),
        rsi_oversold=float(os.getenv("RSI_OVERSOLD", "35")),
        rsi_overbought=float(os.getenv("RSI_OVERBOUGHT", "65")),
        bb_period=int(os.getenv("BB_PERIOD", "20")),
        bb_std=float(os.getenv("BB_STD", "2.0")),

        trade_size_pct=float(os.getenv("TRADE_SIZE_PCT", "20")),
        stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "3.0")),
        take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "6.0")),
        max_open_trades=int(os.getenv("MAX_OPEN_TRADES", "1")),
        max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "10.0")),

        telegram_enabled=_bool(os.getenv("TELEGRAM_ENABLED", "false")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),

        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_file=os.getenv("LOG_FILE", "logs/bot.log"),
    )

    _validate(cfg)
    return cfg


def _validate(cfg: Config):
    if not cfg.paper_trading and (not cfg.api_key or not cfg.api_secret):
        raise ValueError(
            "API_KEY e API_SECRET são obrigatórios quando PAPER_TRADING=false"
        )

    if cfg.ma_fast >= cfg.ma_slow:
        raise ValueError(
            f"MA_FAST ({cfg.ma_fast}) deve ser menor que MA_SLOW ({cfg.ma_slow})"
        )

    supported = ("binance", "bybit", "kucoin")
    if cfg.exchange not in supported:
        raise ValueError(f"Exchange '{cfg.exchange}' não suportada. Use: {supported}")

    if cfg.trade_size_pct <= 0 or cfg.trade_size_pct > 100:
        raise ValueError("TRADE_SIZE_PCT deve estar entre 1 e 100")
