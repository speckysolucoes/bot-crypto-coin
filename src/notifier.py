"""
Notificador Telegram — envia alertas de trades e status
"""

import aiohttp


class Notifier:
    def __init__(self, cfg, logger):
        self.cfg = cfg
        self.logger = logger
        self._base = f"https://api.telegram.org/bot{cfg.telegram_bot_token}"

    async def send(self, text: str):
        if not self.cfg.telegram_enabled or not self.cfg.telegram_bot_token:
            return
        try:
            url = f"{self._base}/sendMessage"
            payload = {
                "chat_id": self.cfg.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        self.logger.warning(f"Telegram: status {resp.status}")
        except Exception as e:
            self.logger.warning(f"Falha ao enviar Telegram: {e}")
