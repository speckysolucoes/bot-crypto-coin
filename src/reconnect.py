"""
Gerenciador de reconexão com backoff exponencial
==================================================
Se a internet cair ou a exchange ficar instável,
o bot tenta reconectar automaticamente com esperas
crescentes para não sobrecarregar a API.

Sequência de espera:
  Tentativa 1: 5s
  Tentativa 2: 10s
  Tentativa 3: 20s
  Tentativa 4: 40s
  Tentativa 5: 80s
  ...até MAX_WAIT (300s = 5 minutos)
"""

import asyncio
import logging
from typing import Callable, Any, Optional


MAX_RETRIES  = 10
BASE_WAIT    = 5      # segundos
MAX_WAIT     = 300    # 5 minutos
MULTIPLIER   = 2.0


class ConnectionError(Exception):
    pass


class ReconnectionManager:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._consecutive_errors = 0
        self._total_reconnections = 0

    def reset(self):
        """Chama após sucesso para zerar o contador de erros."""
        if self._consecutive_errors > 0:
            self.logger.info(f"✅ Conexão restaurada após {self._consecutive_errors} erros.")
        self._consecutive_errors = 0

    def _wait_time(self) -> float:
        wait = min(BASE_WAIT * (MULTIPLIER ** self._consecutive_errors), MAX_WAIT)
        # Adiciona jitter de ±20% para evitar thundering herd
        import random
        jitter = wait * 0.2 * (random.random() * 2 - 1)
        return max(1.0, wait + jitter)

    async def execute(
        self,
        fn: Callable,
        *args,
        label: str = "operação",
        retries: int = MAX_RETRIES,
        **kwargs,
    ) -> Optional[Any]:
        """
        Executa `fn(*args, **kwargs)` com retry automático.
        Retorna o resultado ou None após esgotar as tentativas.
        """
        for attempt in range(1, retries + 1):
            try:
                result = await fn(*args, **kwargs)
                self.reset()
                return result

            except asyncio.CancelledError:
                raise  # Não captura cancelamento intencional

            except Exception as e:
                self._consecutive_errors += 1
                wait = self._wait_time()

                if attempt >= retries:
                    self.logger.error(
                        f"❌ {label} falhou após {retries} tentativas: {e}"
                    )
                    return None

                self.logger.warning(
                    f"⚠️  {label} — tentativa {attempt}/{retries} falhou: {e} "
                    f"| Aguardando {wait:.0f}s..."
                )
                await asyncio.sleep(wait)

        return None

    async def run_with_reconnect(
        self,
        connect_fn: Callable,
        tick_fn: Callable,
        sleep_secs: int,
        notifier=None,
    ):
        """
        Loop principal com reconexão automática.
        Substitui o loop simples do bot para ser resiliente a quedas.
        """
        while True:
            try:
                # Conecta (ou reconecta)
                await connect_fn()
                self._total_reconnections += 1 if self._consecutive_errors > 0 else 0
                self.reset()

                # Executa o tick
                await tick_fn()
                await asyncio.sleep(sleep_secs)

            except asyncio.CancelledError:
                raise

            except Exception as e:
                self._consecutive_errors += 1
                wait = self._wait_time()

                self.logger.error(
                    f"🔌 Erro de conexão (#{self._consecutive_errors}): {e} "
                    f"| Reconectando em {wait:.0f}s..."
                )

                if notifier and self._consecutive_errors == 3:
                    # Só notifica no Telegram após 3 erros seguidos
                    await notifier.send(
                        f"⚠️ Bot perdeu conexão — tentando reconectar\n"
                        f"Erros consecutivos: {self._consecutive_errors}"
                    )

                if self._consecutive_errors >= MAX_RETRIES:
                    msg = f"💀 Bot encerrou após {MAX_RETRIES} falhas consecutivas sem recuperação."
                    self.logger.critical(msg)
                    if notifier:
                        await notifier.send(msg)
                    raise ConnectionError(msg)

                await asyncio.sleep(wait)
