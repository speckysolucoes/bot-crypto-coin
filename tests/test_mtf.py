import logging

import pytest
from unittest.mock import AsyncMock

from src.config import Config
from src.mtf import MultiTimeframeAnalyzer, MTFBias


@pytest.mark.asyncio
async def test_mtf_restores_timeframe_after_fetch_error():
    cfg = Config(
        exchange="binance",
        symbol="BTC/USDT",
        timeframe="15m",
        paper_trading=True,
    )
    log = logging.getLogger("mtf-test")
    conn = AsyncMock()
    conn.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network"))

    cfg.timeframe = "15m"
    mtf = MultiTimeframeAnalyzer(cfg, conn, log)
    bias = await mtf.get_bias()

    assert bias == MTFBias.UNKNOWN
    assert cfg.timeframe == "15m"
