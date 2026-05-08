from src.simulation import (
    PaperState,
    paper_equity,
    paper_finalize_open_position,
    paper_strategy_return_pct,
)


def test_paper_equity_flat():
    s = PaperState(balance=1000.0)
    assert paper_equity(s, 50_000) == 1000.0


def test_paper_equity_in_position():
    s = PaperState(balance=0, asset=0.1, buy_price=90_000, in_position=True)
    assert abs(paper_equity(s, 100_000) - 10_000) < 1e-6


def test_strategy_return_pct():
    assert abs(paper_strategy_return_pct(11_000, 10_000) - 10.0) < 1e-9


def test_finalize_closes_long():
    s = PaperState(balance=5000, asset=0.05, buy_price=100_000, in_position=True)
    s2, recs = paper_finalize_open_position(s, 110_000)
    assert not s2.in_position
    assert s2.asset == 0.0
    assert recs and "pnl" in recs[0]
