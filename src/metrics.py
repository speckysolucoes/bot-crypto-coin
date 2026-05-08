"""Métricas leves em JSON Lines (opcional via BOT_METRICS_JSON)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def metrics_enabled() -> bool:
    v = os.getenv("BOT_METRICS_JSON", "").strip().lower()
    return v in ("1", "true", "yes", "sim")


def append_metric(logger, payload: Dict[str, Any]) -> None:
    """
    Anexa uma linha JSON em logs/bot_metrics.jsonl quando BOT_METRICS_JSON está ativo.
    `logger` recebe um eco em nível DEBUG para aparecer correlacionável no bot.log se quiser.
    """
    if not metrics_enabled():
        return
    line = {"ts": datetime.now(timezone.utc).isoformat(), **payload}
    Path("logs").mkdir(exist_ok=True)
    path = Path("logs") / "bot_metrics.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    logger.debug("metric:%s", json.dumps(line, ensure_ascii=False))
