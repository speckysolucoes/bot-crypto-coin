"""
Scheduler de re-otimização semanal
=====================================
Integra o AutoTuner ao loop do bot, re-otimizando automaticamente
em intervalos configuráveis sem interromper o trading.

Uso standalone (sem o bot principal):
    python -m src.scheduler

Integrado ao bot:
    O bot chama WeeklyScheduler.maybe_run() a cada tick.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from autotune import AutoTuner
from src.config import Config


SCHEDULE_FILE = "logs/schedule_state.json"


class WeeklyScheduler:
    """
    Controla quando rodar o auto-tuner.
    Persiste o estado em disco para sobreviver a reinicializações.
    Na primeira subida não roda tuner imediatamente: aguarda `interval_days`
    até a `run_hour` configurada (evita spike CPU/API ao iniciar).
    """

    def __init__(
        self,
        cfg: Config,
        logger: logging.Logger,
        interval_days: int = 7,
        run_hour: int = 3,
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
        self._first_seen: Optional[datetime] = None
        self._running_now: bool = False
        self._load_state()

    def _load_state(self):
        if Path(SCHEDULE_FILE).exists():
            try:
                with open(SCHEDULE_FILE, encoding="utf-8") as f:
                    state = json.load(f)
                ts = state.get("last_run")
                if ts:
                    self._last_run = datetime.fromisoformat(ts)
                    self.logger.info(
                        "⏰ Scheduler: última otimização em "
                        + self._last_run.strftime("%d/%m/%Y %H:%M")
                    )
                fs = state.get("first_seen")
                if fs:
                    self._first_seen = datetime.fromisoformat(fs)
            except Exception:
                pass

    def _save_state(self):
        Path(SCHEDULE_FILE).parent.mkdir(exist_ok=True)
        payload = {
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "first_seen": self._first_seen.isoformat() if self._first_seen else None,
        }
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _should_run(self) -> bool:
        if self._running_now:
            return False

        now = datetime.now()

        if self._last_run is None:
            if self._first_seen is None:
                self._first_seen = now
                self._save_state()
                self.logger.info(
                    "⏰ Scheduler: primeira subida — auto-tuner não roda ao iniciar; "
                    f"primeira janela após {self.interval_days}d na hora {self.run_hour:02d}h."
                )
                return False
            earliest = self._first_seen + timedelta(days=self.interval_days)
            if now < earliest or now.hour != self.run_hour:
                return False
            return True

        next_run = self._last_run + timedelta(days=self.interval_days)
        return bool(now >= next_run and now.hour == self.run_hour)

    def next_run_str(self) -> str:
        if self._last_run is None and self._first_seen:
            tgt = self._first_seen + timedelta(days=self.interval_days)
            return f"{tgt.strftime('%d/%m/%Y')} (janela {self.run_hour:02d}h)"
        if self._last_run is None:
            return "(aguardando primeira janela após período inicial)"
        next_run = self._last_run + timedelta(days=self.interval_days)
        return next_run.strftime("%d/%m/%Y às %H:%M")

    async def maybe_run(self, bot=None) -> bool:
        """Chamado a cada tick do bot."""
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
                from src.config import load_config

                bot.cfg = load_config()
                self.logger.info("✅ Configurações recarregadas. Bot continua operando.")

            return True

        except Exception as e:
            self.logger.error("Erro no auto-tuner: %s", e, exc_info=True)
            return False
        finally:
            self._running_now = False


async def run_standalone():
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
        run_hour=datetime.now().hour,
    )

    logger.info(
        "🕐 Scheduler iniciado — próxima otimização: %s", scheduler.next_run_str()
    )
    logger.info("   (Ctrl+C para parar)")

    CHECK_INTERVAL = 3600

    while True:
        ran = await scheduler.maybe_run()
        if ran:
            logger.info(
                "✅ Otimização concluída. Próxima: %s", scheduler.next_run_str()
            )
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_standalone())
