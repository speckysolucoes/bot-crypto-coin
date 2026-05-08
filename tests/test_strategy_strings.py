from src.indicators import Indicators, MarketRegime
from src.strategy import Signal, signal_description


def test_signal_description_hold():
    ind = Indicators(
        close=50_000.0,
        regime=MarketRegime.UNKNOWN,
        confidence=42,
        buy_and_hold_pct=2.5,
    )
    text = signal_description(Signal.HOLD, ind)
    assert "AGUARDAR" in text
