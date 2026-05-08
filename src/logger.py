"""
Configuração de logging com saída colorida no terminal e arquivo rotacionado.

Opcional: segundo arquivo apenas JSON Lines quando BOT_JSON_LOG_FILE estiver definido
(ex.: BOT_JSON_LOG_FILE=logs/bot_events.jsonl).
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",    # Ciano
        logging.INFO: "\033[32m",     # Verde
        logging.WARNING: "\033[33m",  # Amarelo
        logging.ERROR: "\033[31m",    # Vermelho
        logging.CRITICAL: "\033[35m", # Magenta
    }
    RESET = "\033[0m"
    FMT = "%(asctime)s [%(levelname)s] %(message)s"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        formatter = logging.Formatter(
            f"{color}{self.FMT}{self.RESET}", datefmt="%Y-%m-%d %H:%M:%S"
        )
        return formatter.format(record)


def setup_logger(name: str = "cryptobot", log_file: str = "logs/bot.log", level: str = "INFO") -> logging.Logger:
    Path("logs").mkdir(exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        # Terminal
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(ColorFormatter())
        logger.addHandler(ch)

        # Arquivo (rotacionado a cada 5MB, mantém 3 backups)
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)

        json_log = os.getenv("BOT_JSON_LOG_FILE", "").strip()
        if json_log:
            Path(json_log).parent.mkdir(parents=True, exist_ok=True)
            jh = logging.FileHandler(json_log, encoding="utf-8")
            jh.setFormatter(JsonLinesFormatter())
            logger.addHandler(jh)

    return logger
