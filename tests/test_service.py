from wx_trade_alert.models import TradeSignal
from wx_trade_alert.service import format_alert


def test_format_alert_contains_core_fields():
    signal = TradeSignal(
        True, "buy", "option", "NVDA", "call", "150", "2026-09-18", "2", confidence=0.93
    )
    text = format_alert(signal, "NVDA 150 call 买两手", 0)
    assert "买入" in text
    assert "NVDA" in text
    assert "CALL" in text
    assert "93%" in text


def test_format_alert_contains_price_and_related_messages():
    signal = TradeSignal.from_dict(
        {"is_trade_signal": True, "action": "buy", "asset_type": "option",
         "symbol": "AAPL", "option_type": "put", "strike": "325",
         "expiry": "9/18", "price": "9.25", "confidence": 0.95}
    )
    text = format_alert(signal, "aapl 9/18 325p | 买9.25的", 0)
    assert "价格 9.25" in text
    assert "关联消息：aapl 9/18 325p | 买9.25的" in text


def test_format_alert_labels_self_report_without_symbol():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "is_self_reported_action": True,
            "action": "reduce",
            "confidence": 0.75,
            "quantity": "一半",
        }
    )
    text = format_alert(signal, "我走了一半", 0)
    assert "类型：本人操作反馈" in text
    assert "标的：消息未明确" in text


def test_format_alert_labels_planned_action_as_message_only():
    signal = TradeSignal.from_dict(
        {
            "is_trade_signal": True,
            "signal_timing": "planned",
            "action": "buy",
            "asset_type": "stock",
            "symbol": "SPY",
            "price": "降到 500",
            "confidence": 0.9,
        }
    )
    text = format_alert(signal, "等到 SPY 降到 500 时买", 0)
    assert text.startswith("【交易预告】")
    assert "类型：预告操作（仅消息）" in text
