from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Settings
from .models import IncomingMessage

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedTargets:
    group_wxid: str
    member_wxid: str
    alert_contact_wxid: str
    self_wxid: str
    self_name: str

    @property
    def target_is_self(self) -> bool:
        return self.member_wxid == self.self_wxid


class WeChatAdapter:
    def __init__(self, settings: Settings, require_gui: bool = False):
        self.settings = settings
        from wechatauto import WeChatDB

        self.db = WeChatDB()
        self.targets = self._resolve_targets()
        self._media = None
        self._wx = None
        self._listener = None
        if require_gui:
            self._ensure_gui()

    def _resolve_targets(self) -> ResolvedTargets:
        info = self.db.get_self_info()
        groups = [g for g in self.db.get_groups() if g.get("name") == self.settings.group_name]
        if len(groups) != 1:
            raise RuntimeError(
                f"群聊“{self.settings.group_name}”精确匹配到 {len(groups)} 个；需要恰好 1 个"
            )
        group_wxid = groups[0]["username"]
        members = self.db.get_group_members(group_wxid)
        matches = [
            m for m in members
            if self.settings.target_member in {m.get("nick_name", ""), m.get("remark", "")}
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"群成员“{self.settings.target_member}”精确匹配到 {len(matches)} 个；需要恰好 1 个"
            )
        contact_hits = self.db.search_contact(self.settings.alert_contact_remark)
        contacts_by_id = {
            c["username"]: c for c in contact_hits
            if c.get("remark") == self.settings.alert_contact_remark
            or c.get("nick_name") == self.settings.alert_contact_nickname
        }
        contacts = list(contacts_by_id.values())
        if len(contacts) != 1:
            raise RuntimeError(
                f"接警联系人“{self.settings.alert_contact_remark}”精确匹配到 {len(contacts)} 个；需要恰好 1 个"
            )
        return ResolvedTargets(
            group_wxid=group_wxid,
            member_wxid=matches[0]["username"],
            alert_contact_wxid=contacts[0]["username"],
            self_wxid=info.get("username") or "",
            self_name=info.get("nick_name") or info.get("username") or "未知账号",
        )

    def _ensure_gui(self):
        if self._wx is None:
            from wechatauto import WeChat

            self._wx = WeChat()
        return self._wx

    def start_listener(self, callback: Callable[[IncomingMessage], None]) -> None:
        from wechatauto.db import Listener

        def on_raw(raw: dict, _listener) -> None:
            sender = str(raw.get("sender_username") or "")
            sender_id = int(raw.get("sender_id") or 0)
            is_target = sender in {self.targets.member_wxid, self.settings.target_member}
            if self.targets.target_is_self and sender_id == 2:
                is_target = True
                sender = self.targets.self_wxid
            if not is_target:
                return
            event = IncomingMessage(
                chat_wxid=self.targets.group_wxid,
                local_id=int(raw.get("local_id") or 0),
                sort_seq=int(raw.get("sort_seq") or 0),
                msg_type=str(raw.get("type") or raw.get("local_type") or ""),
                sender_username=sender,
                create_time=float(raw.get("create_time") or time.time()),
                content=str(raw.get("content") or ""),
            )
            callback(event)

        self._listener = Listener(
            self.db,
            interval=self.settings.listener_interval_seconds,
            watermark_file=str(self.settings.watermark_file),
            max_retries=3,
        )
        self._listener.add_listener(self.targets.group_wxid, on_raw)
        self._listener.start()

    def stop_listener(self) -> None:
        if self._listener:
            self._listener.stop()

    def download_voice(self, local_id: int) -> str:
        if self._media is None:
            from wechatauto.media import MediaDownloader

            self._media = MediaDownloader(self.db)
        for attempt in range(self.settings.voice_download_retries):
            path = self._media.download_voice(
                self.targets.group_wxid,
                local_id,
                save_dir=str(self.settings.audio_dir),
            )
            if path:
                return path
            if attempt + 1 < self.settings.voice_download_retries:
                time.sleep(self.settings.voice_download_retry_seconds)
        raise RuntimeError(f"语音文件下载失败：local_id={local_id}")

    def send_message(self, text: str) -> tuple[bool, str]:
        if self.settings.dry_run or not self.settings.send_alert_message:
            LOG.warning("DRY-RUN：本应向 %s 发送：%s", self.settings.alert_contact_remark, text)
            return True, "dry-run"
        result = self._ensure_gui().SendMsg(text, self.settings.alert_contact_remark)
        return bool(result), str(result)

    def voice_call(self) -> tuple[bool, str]:
        if self.settings.dry_run or not self.settings.calls_enabled:
            LOG.warning("DRY-RUN：本应呼叫 %s", self.settings.alert_contact_remark)
            return True, "dry-run"
        result = self._ensure_gui().VoiceCall(self.settings.alert_contact_remark, video=False)
        return bool(result), str(result)
