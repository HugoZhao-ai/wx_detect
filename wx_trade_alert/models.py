from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ALLOWED_ACTIONS = {
    "buy", "sell", "short", "cover", "add", "reduce", "open", "close",
    "roll", "exercise", "cancel", "hold", "unknown",
}
ALLOWED_ASSETS = {"stock", "option", "unknown"}
ALLOWED_OPTION_TYPES = {"call", "put", "unknown", ""}


@dataclass(frozen=True)
class TradeSignal:
    is_trade_signal: bool
    action: str = "unknown"
    asset_type: str = "unknown"
    symbol: str = ""
    option_type: str = ""
    strike: str = ""
    expiry: str = ""
    quantity: str = ""
    urgency: str = "normal"
    confidence: float = 0.0
    evidence: str = ""
    reason: str = ""
    price: str = ""
    is_self_reported_action: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TradeSignal":
        if not isinstance(value, dict):
            raise ValueError("模型输出必须是 JSON 对象")
        truth = value.get("is_trade_signal", False)
        if not isinstance(truth, bool):
            raise ValueError("is_trade_signal 必须是布尔值")
        action = str(value.get("action", "unknown")).strip().lower()
        asset = str(value.get("asset_type", "unknown")).strip().lower()
        option_type = str(value.get("option_type", "")).strip().lower()
        if action not in ALLOWED_ACTIONS:
            action = "unknown"
        if asset not in ALLOWED_ASSETS:
            asset = "unknown"
        if option_type not in ALLOWED_OPTION_TYPES:
            option_type = "unknown"
        try:
            confidence = min(1.0, max(0.0, float(value.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        return cls(
            is_trade_signal=truth,
            action=action,
            asset_type=asset,
            symbol=str(value.get("symbol", "")).strip().upper(),
            option_type=option_type,
            strike=str(value.get("strike", "")).strip(),
            expiry=str(value.get("expiry", "")).strip(),
            quantity=str(value.get("quantity", "")).strip(),
            urgency=str(value.get("urgency", "normal")).strip().lower(),
            confidence=confidence,
            evidence=str(value.get("evidence", "")).strip()[:300],
            reason=str(value.get("reason", "")).strip()[:500],
            price=str(value.get("price", "")).strip()[:80],
            is_self_reported_action=value.get("is_self_reported_action") is True,
        )

    def should_alert(self, threshold: float) -> bool:
        has_instrument = self.asset_type in {"stock", "option"} and bool(self.symbol)
        return (
            self.is_trade_signal
            and self.confidence >= threshold
            and self.action not in {"unknown", "hold"}
            and (has_instrument or self.is_self_reported_action)
        )

    def fingerprint(self) -> str:
        core = {
            "action": self.action,
            "asset_type": self.asset_type,
            "symbol": self.symbol,
            "option_type": self.option_type,
            "strike": self.strike,
            "expiry": self.expiry,
            "quantity": self.quantity,
        }
        raw = json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class IncomingMessage:
    chat_wxid: str
    local_id: int
    sort_seq: int
    msg_type: str
    sender_username: str
    create_time: float
    content: str
