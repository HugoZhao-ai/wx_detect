from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import Settings
from .detector import DeepSeekDetector
from .models import IncomingMessage, TradeSignal
from .session_log import SessionMessageLog
from .speech import SpeechTranscriber
from .state import StateStore
from .wechat_adapter import WeChatAdapter

LOG = logging.getLogger(__name__)
TEXT_TYPE = "文本"
VOICE_TYPE = "语音"


def format_alert(signal: TradeSignal, source: str, occurred_at: float) -> str:
    action_labels = {
        "buy": "买入", "sell": "卖出", "short": "做空", "cover": "回补",
        "add": "加仓", "reduce": "减仓", "open": "开仓", "close": "平仓",
        "roll": "滚仓", "exercise": "行权", "cancel": "撤单",
    }
    alert_kind = "本人操作反馈" if signal.is_self_reported_action else "交易指令"
    asset = "期权" if signal.asset_type == "option" else "股票"
    option = f" {signal.option_type.upper()}" if signal.option_type in {"call", "put"} else ""
    detail_parts = []
    if signal.expiry:
        detail_parts.append(f"到期 {signal.expiry}")
    if signal.strike:
        detail_parts.append(f"行权价 {signal.strike}")
    if signal.price:
        detail_parts.append(f"价格 {signal.price}")
    if signal.quantity:
        detail_parts.append(f"数量 {signal.quantity}")
    extras = "；".join(detail_parts)
    at = datetime.fromtimestamp(occurred_at).strftime("%Y-%m-%d %H:%M:%S")
    instrument = (
        f"{signal.symbol} {asset}{option}"
        if signal.symbol
        else "消息未明确"
    )
    return (
        "【交易动作告警】\n"
        f"时间：{at}\n"
        f"类型：{alert_kind}\n"
        f"动作：{action_labels.get(signal.action, signal.action)}\n"
        f"标的：{instrument}\n"
        f"细节：{extras or '消息未提供'}\n"
        f"置信度：{signal.confidence:.0%}\n"
        f"关联消息：{source[:300]}"
    )


class MonitorService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state = StateStore(settings.state_db)
        self.detector = DeepSeekDetector(settings)
        self.transcriber = SpeechTranscriber(settings)
        self.wechat = WeChatAdapter(settings)
        self.stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self.session_log: SessionMessageLog | None = None

    def start(self) -> None:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("请先在 .env 中配置新的 DEEPSEEK_API_KEY")
        self.session_log = SessionMessageLog.create(
            self.settings.session_dir,
            self.settings.group_name,
            self.settings.target_member,
        )
        LOG.info("本次会话 JSON：%s", self.session_log.path)
        self._worker = threading.Thread(target=self._worker_loop, name="signal-worker", daemon=True)
        self._worker.start()
        self.wechat.start_listener(self._on_message)
        LOG.info(
            "已开始监听群“%s”中的“%s”（dry_run=%s, calls=%s）",
            self.settings.group_name,
            self.settings.target_member,
            self.settings.dry_run,
            self.settings.calls_enabled,
        )

    def stop(self) -> None:
        self.stop_event.set()
        self.wechat.stop_listener()
        if self._worker:
            self._worker.join(timeout=10)

    def _on_message(self, message: IncomingMessage) -> None:
        if message.msg_type not in {TEXT_TYPE, VOICE_TYPE}:
            LOG.debug("忽略非文本/语音消息 type=%s", message.msg_type)
            return
        if self.state.enqueue(message):
            preview = (
                message.content.strip().replace("\n", " ")[:120]
                if message.msg_type == TEXT_TYPE
                else "[语音消息，等待转写]"
            )
            LOG.info(
                "抓到目标消息：local_id=%s type=%s sender=%s content=%s",
                message.local_id,
                message.msg_type,
                message.sender_username,
                preview,
            )

    def _worker_loop(self) -> None:
        next_heartbeat = time.monotonic()
        while not self.stop_event.is_set():
            row = self.state.claim_next()
            if row is None:
                if time.monotonic() >= next_heartbeat:
                    LOG.info("监控心跳：监听线程正常，队列状态=%s", self.state.status_counts())
                    next_heartbeat = time.monotonic() + 60
                self.stop_event.wait(0.5)
                continue
            try:
                self._process(row)
                self.state.mark_done(row["id"])
            except Exception as exc:
                LOG.exception("处理消息 %s 失败", row["id"])
                self.state.mark_failed(
                    row["id"], str(exc), retry=(int(row["attempts"]) + 1) < 3
                )
                self.stop_event.wait(min(10, 2 ** int(row["attempts"])))

    def _process(self, row) -> None:
        source = str(row["content"] or "").strip()
        audio_path: Path | None = None
        if str(row["msg_type"]) == VOICE_TYPE:
            audio_path = Path(self.wechat.download_voice(int(row["local_id"])))
            source = self.transcriber.transcribe_silk(audio_path)
            LOG.info("语音转写：%s", source)
        if not source:
            LOG.info("消息没有可分析文本，跳过")
            return
        if self.session_log is None:
            raise RuntimeError("本次会话 JSON 尚未初始化")
        message = IncomingMessage(
            chat_wxid=str(row["chat_wxid"]),
            local_id=int(row["local_id"]),
            sort_seq=int(row["sort_seq"]),
            msg_type=str(row["msg_type"]),
            sender_username=str(row["sender_username"]),
            create_time=float(row["create_time"]),
            content=source,
        )
        session_data = self.session_log.append_message(message, source)
        LOG.info(
            "已写入会话 JSON：messages=%d latest=%s",
            len(session_data["messages"]),
            session_data["latest_message_key"],
        )
        signal = self.detector.classify_session(session_data)
        should_alert = signal.should_alert(self.settings.confidence_threshold)
        LOG.info(
            "模型判定：confidence=%.3f threshold=%.3f should_alert=%s action=%s "
            "asset=%s symbol=%s result=%s",
            signal.confidence,
            self.settings.confidence_threshold,
            should_alert,
            signal.action,
            signal.asset_type,
            signal.symbol or "-",
            signal.to_json(),
        )
        if not should_alert:
            self._cleanup_audio(audio_path)
            return
        fingerprint = signal.fingerprint()
        if self.state.is_duplicate(fingerprint, self.settings.dedupe_minutes * 60):
            LOG.warning("命中 %d 分钟去重窗口，不重复告警", self.settings.dedupe_minutes)
            self._cleanup_audio(audio_path)
            return
        signal_id = self.state.record_signal(int(row["id"]), signal)
        related_source = signal.evidence or source
        alert_text = format_alert(signal, related_source, float(row["create_time"]))
        msg_ok, msg_detail = self.wechat.send_message(alert_text)
        LOG.info("告警消息发送结果：%s %s", msg_ok, msg_detail)
        self.state.mark_alerted(signal_id)
        self._place_call(signal_id)
        self._cleanup_audio(audio_path)

    def _place_call(self, signal_id: int) -> None:
        if self.state.calls_in_last_hour() >= self.settings.calls_per_hour:
            LOG.error("已达到每小时 %d 次通话上限，停止呼叫", self.settings.calls_per_hour)
            return
        for attempt in range(self.settings.call_max_attempts):
            ok, detail = self.wechat.voice_call()
            self.state.record_call(signal_id, ok, detail)
            LOG.info("呼叫第 %d 次：%s %s", attempt + 1, ok, detail)
            if ok:
                return
            if attempt + 1 < self.settings.call_max_attempts:
                self.stop_event.wait(self.settings.call_retry_seconds)

    def _cleanup_audio(self, path: Path | None) -> None:
        if not path or self.settings.keep_voice_hours > 0:
            return
        path.unlink(missing_ok=True)
