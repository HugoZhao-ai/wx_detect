from wx_trade_alert.models import TradeSignal


def test_obvious_option_signal_alerts():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "action": "buy",
            "asset_type": "option",
            "symbol": "nvda",
            "option_type": "call",
            "strike": "150",
            "expiry": "2026-09-18",
            "quantity": "2",
            "confidence": 0.96,
        }
    )
    assert signal.symbol == "NVDA"
    assert signal.should_alert(0.85)


def test_question_does_not_alert():
    signal = TradeSignal.from_dict(
        {"is_trade_signal": False, "confidence": 0.99, "symbol": "TSLA", "action": "buy"}
    )
    assert not signal.should_alert(0.85)


def test_unknown_symbol_does_not_alert():
    signal = TradeSignal.from_dict(
        {"is_trade_signal": True, "confidence": 0.99, "asset_type": "stock", "action": "buy"}
    )
    assert not signal.should_alert(0.85)


def test_fingerprint_ignores_explanation():
    a = TradeSignal(True, "buy", "stock", "AAPL", confidence=0.9, reason="a")
    b = TradeSignal(True, "buy", "stock", "AAPL", confidence=0.95, reason="b")
    assert a.fingerprint() == b.fingerprint()


def test_price_is_parsed_but_does_not_change_dedupe_identity():
    a = TradeSignal.from_dict(
        {"is_trade_signal": True, "action": "buy", "asset_type": "option",
         "symbol": "AAPL", "option_type": "put", "strike": "325", "price": "9.25"}
    )
    b = TradeSignal.from_dict(
        {"is_trade_signal": True, "action": "buy", "asset_type": "option",
         "symbol": "AAPL", "option_type": "put", "strike": "325", "price": "9.30"}
    )
    assert a.price == "9.25"
    assert a.fingerprint() == b.fingerprint()
