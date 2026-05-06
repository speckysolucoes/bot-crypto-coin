"""
CryptoBot - Bot de Trading de Criptomoedas
Estratégia: Cruzamento de Médias Móveis + RSI + Bandas de Bollinger

Suporte a exchanges: Binance, Bybit, KuCoin (via ccxt)

⚠️  AVISO: Use por sua conta e risco. Teste sempre em modo paper trading antes.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

from src.bot import TradingBot
from src.config import load_config
from src.logger import setup_logger


def handle_shutdown(signum, frame):
    print("\n\n⏹  Sinal de encerramento recebido. Finalizando bot...")
    sys.exit(0)


async def main():
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger = setup_logger()
    logger.info("=" * 60)
    logger.info("  CryptoBot v1.0 - Iniciando...")
    logger.info("=" * 60)

    config = load_config()
    bot = TradingBot(config, logger)

    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
