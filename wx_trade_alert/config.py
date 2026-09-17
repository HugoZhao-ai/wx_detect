from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _as_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc


def _as_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    group_name: str
    target_member: str
    alert_contact_remark: str
    alert_contact_nickname: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    deepseek_timeout_seconds: float
    confidence_threshold: float
    dedupe_minutes: int
    calls_per_hour: int
    call_max_attempts: int
    call_retry_seconds: int
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    silk_sample_rate: int
    voice_download_retries: int
    voice_download_retry_seconds: float
    keep_voice_hours: int
    listener_interval_seconds: float
    context_messages: int
    context_window_seconds: int
    calls_enabled: bool
    send_alert_message: bool
    dry_run: bool
    log_level: str

    @property
    def data_dir(self) -> Path:
        return self.project_dir / "data"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def state_db(self) -> Path:
        return self.data_dir / "state.db"

    @property
    def watermark_file(self) -> Path:
        return self.data_dir / "listener_watermark.json"

    @classmethod
    def load(cls, project_dir: Path | None = None) -> "Settings":
        root = (project_dir or Path(__file__).resolve().parents[1]).resolve()
        try:
            from dotenv import load_dotenv

            load_dotenv(root / ".env", override=False)
        except ImportError:
            pass

        settings = cls(
            project_dir=root,
            group_name=os.getenv("WECHAT_GROUP_NAME", "多空双杀华尔街").strip(),
            target_member=os.getenv("WECHAT_TARGET_MEMBER", "吹峰机").strip(),
            alert_contact_remark=os.getenv("WECHAT_ALERT_CONTACT_REMARK", "王庆鹏").strip(),
            alert_contact_nickname=os.getenv("WECHAT_ALERT_CONTACT_NICKNAME", "Windy & Warm").strip(),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip(),
            deepseek_timeout_seconds=_as_float("DEEPSEEK_TIMEOUT_SECONDS", 30),
            confidence_threshold=_as_float("ALERT_CONFIDENCE_THRESHOLD", 0.85),
            dedupe_minutes=_as_int("DEDUPE_MINUTES", 10),
            calls_per_hour=_as_int("CALLS_PER_HOUR", 5),
            call_max_attempts=_as_int("CALL_MAX_ATTEMPTS", 2),
            call_retry_seconds=_as_int("CALL_RETRY_SECONDS", 60),
            whisper_model=os.getenv("WHISPER_MODEL", "small").strip(),
            whisper_device=os.getenv("WHISPER_DEVICE", "cpu").strip(),
            whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip(),
            silk_sample_rate=_as_int("SILK_SAMPLE_RATE", 24000),
            voice_download_retries=_as_int("VOICE_DOWNLOAD_RETRIES", 6),
            voice_download_retry_seconds=_as_float("VOICE_DOWNLOAD_RETRY_SECONDS", 2),
            keep_voice_hours=_as_int("KEEP_VOICE_HOURS", 24),
            listener_interval_seconds=_as_float("LISTENER_INTERVAL_SECONDS", 0.8),
            context_messages=_as_int("TARGET_CONTEXT_MESSAGES", 8),
            context_window_seconds=_as_int("TARGET_CONTEXT_WINDOW_SECONDS", 300),
            calls_enabled=_as_bool("CALLS_ENABLED", False),
            send_alert_message=_as_bool("SEND_ALERT_MESSAGE", True),
            dry_run=_as_bool("DRY_RUN", True),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
        settings.validate()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.audio_dir.mkdir(parents=True, exist_ok=True)
        return settings

    def validate(self) -> None:
        if not self.group_name or not self.target_member or not self.alert_contact_remark:
            raise ValueError("群名、监听成员和接警联系人不能为空")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("ALERT_CONFIDENCE_THRESHOLD 必须在 0 到 1 之间")
        if self.calls_per_hour < 1 or self.call_max_attempts < 1:
            raise ValueError("通话限额和尝试次数必须大于 0")
        if self.context_messages < 1 or self.context_window_seconds < 1:
            raise ValueError("上下文消息数和时间窗口必须大于 0")
        if self.silk_sample_rate not in {8000, 12000, 16000, 24000, 32000, 44100, 48000}:
            raise ValueError("SILK_SAMPLE_RATE 不是受支持的采样率")
