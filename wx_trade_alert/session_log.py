from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from .models import IncomingMessage


class SessionMessageLog:
    def __init__(self, path: Path, payload: dict):
        self.path = path
        self._payload = payload
        self._lock = threading.RLock()

    @classmethod
    def create(
        cls,
        directory: Path,
        group_name: str,
        target_member: str,
        started_at: datetime | None = None,
    ) -> "SessionMessageLog":
        directory.mkdir(parents=True, exist_ok=True)
        started = started_at or datetime.now().astimezone()
        stem = started.strftime("%Y-%m-%d_%H-%M-%S")
        path = directory / f"{stem}.json"
        suffix = 2
        while path.exists():
            path = directory / f"{stem}_{suffix}.json"
            suffix += 1
        payload = {
            "schema_version": 1,
            "session_started_at": started.isoformat(timespec="seconds"),
            "group_name": group_name,
            "target_member": target_member,
            "latest_message_key": "",
            "messages": [],
        }
        result = cls(path, payload)
        result._write()
        return result

    def append_message(self, message: IncomingMessage, text: str) -> dict:
        key = f"{message.chat_wxid}:{message.local_id}:{message.sort_seq}"
        with self._lock:
            existing = next(
                (item for item in self._payload["messages"] if item["key"] == key),
                None,
            )
            if existing is None:
                spoken_at = datetime.fromtimestamp(
                    message.create_time
                ).astimezone().isoformat(timespec="seconds")
                self._payload["messages"].append(
                    {
                        "key": key,
                        "local_id": message.local_id,
                        "sort_seq": message.sort_seq,
                        "message_type": message.msg_type,
                        "sender_username": message.sender_username,
                        "spoken_at": spoken_at,
                        "text": text,
                    }
                )
                self._payload["messages"].sort(
                    key=lambda item: (item["sort_seq"], item["local_id"])
                )
            self._payload["latest_message_key"] = key
            self._write()
            return copy.deepcopy(self._payload)

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._payload)

    def _write(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(self._payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, self.path)
