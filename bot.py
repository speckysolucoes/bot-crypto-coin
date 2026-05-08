"""
CryptoBot - Bot de Trading de Criptomoedas
Estratégia: Cruzamento de Médias Móveis + RSI + Bandas de Bollinger

Suporte a exchanges: Binance, Bybit, KuCoin (via ccxt)

⚠️  AVISO: Use por sua conta e risco. Teste sempre em modo paper trading antes.
"""

import asyncio
import signal
import sys

from src.bot import TradingBot
from src.config import load_config
from src.logger import setup_logger


async def async_main():
    logger = setup_logger()
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    def queue_shutdown(signum=None, frame=None):
        print("\n\n⏹  Sinal de encerramento recebido. Finalizando bot...")
        loop.call_soon_threadsafe(shutdown.set)

    try:
        signal.signal(signal.SIGINT, queue_shutdown)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, queue_shutdown)
    except ValueError:
        logger.warning("Sinais POSIX indisponíveis neste contexto.")

    logger.info("=" * 60)
    logger.info("  CryptoBot v1.0 - Iniciando...")
    logger.info("=" * 60)

    config = load_config()
    bot = TradingBot(config, logger, shutdown_event=shutdown)

    fatal = False
    try:
        runner = asyncio.create_task(bot.run())
        wait_shutdown = asyncio.create_task(shutdown.wait())
        done, pending = await asyncio.wait(
            {runner, wait_shutdown}, return_when=asyncio.FIRST_COMPLETED
        )
        bot.running = False
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário.")
        bot.running = False
    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        fatal = True
        bot.running = False
    finally:
        await bot.shutdown()
        if fatal:
            sys.exit(1)


def main_entry():
    """Ponto de entrada síncrono (console scripts / setuptools)."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main_entry()
