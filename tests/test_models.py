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


def test_immediate_action_without_symbol_notifies_and_calls():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "signal_timing": "immediate",
            "confidence": 0.99,
            "asset_type": "unknown",
            "action": "buy",
        }
    )
    assert signal.should_notify(0.85)
    assert signal.should_call(0.85)


def test_self_reported_action_alerts_without_symbol():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "is_self_reported_action": True,
            "confidence": 0.70,
            "asset_type": "option",
            "action": "reduce",
            "quantity": "一半",
            "evidence": "我走了一半",
        }
    )
    assert signal.should_alert(0.70)


def test_self_reported_action_still_respects_threshold():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "is_self_reported_action": True,
            "confidence": 0.69,
            "action": "reduce",
        }
    )
    assert not signal.should_alert(0.70)


def test_planned_action_notifies_without_calling():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "signal_timing": "planned",
            "confidence": 0.9,
            "asset_type": "stock",
            "symbol": "SPY",
            "action": "buy",
        }
    )
    assert signal.should_notify(0.70)
    assert not signal.should_call(0.70)


def test_historical_action_neither_notifies_nor_calls():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "signal_timing": "historical",
            "confidence": 0.95,
            "action": "buy",
            "quantity": "80",
        }
    )
    assert not signal.should_notify(0.70)
    assert not signal.should_call(0.70)


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
