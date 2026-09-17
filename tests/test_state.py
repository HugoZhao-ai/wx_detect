from pathlib import Path

from wx_trade_alert.models import IncomingMessage, TradeSignal
from wx_trade_alert.state import StateStore


def test_enqueue_is_idempotent(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    msg = IncomingMessage("g", 1, 2, "文本", "u", 123.0, "buy AAPL")
    assert store.enqueue(msg)
    assert not store.enqueue(msg)


def test_duplicate_window(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    msg = IncomingMessage("g", 1, 2, "文本", "u", 123.0, "buy AAPL")
    store.enqueue(msg)
    row = store.claim_next()
    signal = TradeSignal(True, "buy", "stock", "AAPL", confidence=0.9)
    signal_id = store.record_signal(row["id"], signal)
    assert not store.is_duplicate(signal.fingerprint(), 600)
    store.mark_alerted(signal_id)
    assert store.is_duplicate(signal.fingerprint(), 600)


def test_context_respects_age_window(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    store.add_context("old", keep=8, created_at=1.0)
    store.add_context("new", keep=8)
    assert store.get_context(8, max_age_seconds=300) == ["new"]
