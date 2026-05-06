"""
Scheduler de re-otimização semanal
=====================================
Integra o AutoTuner ao loop do bot, re-otimizando automaticamente
em intervalos configuráveis sem interromper o trading.

Uso standalone (sem o bot principal):
    python scheduler.py

Integrado ao bot:
    O bot.py chama WeeklyScheduler.maybe_run() a cada tick.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import Config
from autotune import AutoTuner


SCHEDULE_FILE = "logs/schedule_state.json"


class WeeklyScheduler:
    """
    Controla quando rodar o auto-tuner.
    Persiste o estado em disco para sobreviver a reinicializações.
    """

    def __init__(
        self,
        cfg: Config,
        logger: logging.Logger,
        interval_days: int = 7,
        run_hour: int = 3,          # Hora do dia para rodar (3h da manhã)
        train_days: int = 60,
        val_days: int = 14,
        population: int = 40,
        generations: int = 25,
        min_val_return: float = 0.0,
        restart_bot_after: bool = True,
    ):
        self.cfg = cfg
        self.logger = logger
        self.interval_days = interval_days
        self.run_hour = run_hour
        self.train_days = train_days
        self.val_days = val_days
        self.population = population
        self.generations = generations
        self.min_val_return = min_val_return
        self.restart_bot_after = restart_bot_after

        self._last_run: Optional[datetime] = None
        self._running_now: bool = False
        self._load_state()

    # ── Estado persistido ─────────────────────────────────────────────────────

    def _load_state(self):
        if Path(SCHEDULE_FILE).exists():
            try:
                with open(SCHEDULE_FILE) as f:
                    state = json.load(f)
                ts = state.get("last_run")
                if ts:
                    self._last_run = datetime.fromisoformat(ts)
                    self.logger.info(
                        f"⏰ Scheduler: última otimização em {self._last_run.strftime('%d/%m/%Y %H:%M')}"
                    )
            except Exception:
                pass

    def _save_state(self):
        Path(SCHEDULE_FILE).parent.mkdir(exist_ok=True)
        with open(SCHEDULE_FILE, "w") as f:
            json.dump(
                {"last_run": self._last_run.isoformat() if self._last_run else None},
                f,
                indent=2,
            )

    # ── Verificação de agendamento ────────────────────────────────────────────

    def _should_run(self) -> bool:
        if self._running_now:
            return False

        now = datetime.now()

        # Ainda não rodou nunca → roda agora
        if self._last_run is None:
            return True

        next_run = self._last_run + timedelta(days=self.interval_days)

        # Chegou a hora E estamos na janela da hora configurada
        if now >= next_run and now.hour == self.run_hour:
            return True

        # Passou da data mas fora da janela → aguarda
        return False

    def next_run_str(self) -> str:
        if self._last_run is None:
            return "assim que possível"
        next_run = self._last_run + timedelta(days=self.interval_days)
        return next_run.strftime("%d/%m/%Y às %H:%M")

    # ── Execução ──────────────────────────────────────────────────────────────

    async def maybe_run(self, bot=None) -> bool:
        """
        Chamado a cada tick do bot.
        Retorna True se rodou a otimização.
        """
        if not self._should_run():
            return False

        self._running_now = True
        self.logger.info("⏰ Scheduler: hora de rodar o auto-tuner!")

        try:
            tuner = AutoTuner(
                cfg=self.cfg,
                logger=self.logger,
                train_days=self.train_days,
                val_days=self.val_days,
                population=self.population,
                generations=self.generations,
                min_val_return=self.min_val_return,
            )
            best = await tuner.run(update_env_file=True)

            self._last_run = datetime.now()
            self._save_state()

            if best and self.restart_bot_after and bot is not None:
                self.logger.info(
                    "🔄 Parâmetros atualizados — recarregando configurações do bot..."
                )
                # Recarrega o config sem parar o bot
                from src.config import load_config
                new_cfg = load_config()
                bot.cfg = new_cfg
                self.logger.info("✅ Configurações recarregadas. Bot continua operando.")

            return True

        except Exception as e:
            self.logger.error(f"Erro no auto-tuner: {e}", exc_info=True)
            return False
        finally:
            self._running_now = False


# ── Modo standalone ───────────────────────────────────────────────────────────

async def run_standalone():
    """Roda o scheduler em loop standalone, sem o bot principal."""
    import os
    from src.config import load_config
    from src.logger import setup_logger

    os.environ.setdefault("PAPER_TRADING", "true")
    logger = setup_logger()
    cfg = load_config()

    scheduler = WeeklyScheduler(
        cfg=cfg,
        logger=logger,
        interval_days=7,
        run_hour=datetime.now().hour,  # Roda na hora atual para teste
    )

    logger.info(f"🕐 Scheduler iniciado — próxima otimização: {scheduler.next_run_str()}")
    logger.info("   (Ctrl+C para parar)")

    CHECK_INTERVAL = 3600  # Verifica a cada hora

    while True:
        ran = await scheduler.maybe_run()
        if ran:
            logger.info(f"✅ Otimização concluída. Próxima: {scheduler.next_run_str()}")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_standalone())
