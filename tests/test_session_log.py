import json
from datetime import datetime, timezone
from pathlib import Path

from wx_trade_alert.models import IncomingMessage
from wx_trade_alert.session_log import SessionMessageLog


def test_session_log_creates_new_dated_file_for_each_start(tmp_path: Path):
    started = datetime(2026, 9, 18, 10, 20, 30, tzinfo=timezone.utc)
    first = SessionMessageLog.create(tmp_path, "group", "member", started)
    second = SessionMessageLog.create(tmp_path, "group", "member", started)
    assert first.path.name == "2026-09-18_10-20-30.json"
    assert second.path.name == "2026-09-18_10-20-30_2.json"


def test_session_log_appends_messages_idempotently(tmp_path: Path):
    log = SessionMessageLog.create(tmp_path, "group", "member")
    message = IncomingMessage(
        "group-id", 12, 34, "文本", "member-id", 1_700_000_000, "ignored"
    )
    first = log.append_message(message, "我走了一半")
    second = log.append_message(message, "我走了一半")

    assert first == second
    assert len(second["messages"]) == 1
    assert second["latest_message_key"] == "group-id:12:34"
    spoken_at = datetime.fromisoformat(second["messages"][0]["spoken_at"])
    assert spoken_at.timestamp() == message.create_time
    assert second["messages"][0]["text"] == "我走了一半"
    assert json.loads(log.path.read_text(encoding="utf-8")) == second
