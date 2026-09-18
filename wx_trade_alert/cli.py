from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings
from .detector import DeepSeekDetector
from .models import IncomingMessage
from .service import MonitorService, format_alert
from .state import StateStore
from .wechat_adapter import WeChatAdapter


def setup_logging(level: str, project_dir: Path) -> None:
    log_dir = project_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, level, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s | %(message)s"
    )
    root_stream_handler = logging.StreamHandler(sys.stdout)
    root_stream_handler.setFormatter(formatter)
    package_stream_handler = logging.StreamHandler(sys.stdout)
    package_stream_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        log_dir / "monitor.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logging.basicConfig(
        level=log_level,
        handlers=[root_stream_handler],
        force=True,
    )
    package_logger = logging.getLogger("wx_trade_alert")
    package_logger.handlers.clear()
    package_logger.setLevel(log_level)
    package_logger.addHandler(package_stream_handler)
    package_logger.addHandler(file_handler)
    package_logger.propagate = False


def doctor(settings: Settings) -> int:
    adapter = WeChatAdapter(settings)
    targets = adapter.targets
    print("[OK] 微信数据库可读取")
    print(f"[OK] 当前账号：{targets.self_name}")
    print(f"[OK] 群聊：{settings.group_name} -> {targets.group_wxid}")
    print(f"[OK] 监听成员：{settings.target_member} -> {targets.member_wxid}")
    mode = "监听当前账号自己的群消息" if targets.target_is_self else "监听另一位群成员"
    print(f"[OK] 监听模式：{mode}")
    print(f"[OK] 接警联系人：{settings.alert_contact_remark} -> {targets.alert_contact_wxid}")
    print(f"[{'OK' if settings.deepseek_api_key else '待配置'}] DeepSeek API Key")
    print(f"[安全状态] DRY_RUN={settings.dry_run}, CALLS_ENABLED={settings.calls_enabled}")
    return 0


def probe(settings: Settings, seconds: int) -> int:
    adapter = WeChatAdapter(settings)
    count = 0

    def on_message(msg: IncomingMessage) -> None:
        nonlocal count
        count += 1
        print(
            json.dumps(
                {
                    "local_id": msg.local_id,
                    "type": msg.msg_type,
                    "sender_username": msg.sender_username,
                    "content_preview": msg.content[:100],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    adapter.start_listener(on_message)
    print(f"只读探针已启动，等待 {seconds} 秒；不会调用模型、发消息或打电话。")
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass
    finally:
        adapter.stop_listener()
    print(f"探针结束，捕获目标成员文本/语音消息 {count} 条。")
    return 0


def test_classify(settings: Settings, text: str) -> int:
    signal = DeepSeekDetector(settings).classify(text, [])
    print(signal.to_json())
    print(f"发送告警消息：{signal.should_notify(settings.confidence_threshold)}")
    print(f"发起语音通话：{signal.should_call(settings.confidence_threshold)}")
    return 0


def test_alert(settings: Settings, place_call: bool) -> int:
    adapter = WeChatAdapter(settings, require_gui=True)
    message = "【系统测试】微信交易告警链路测试；这不是实际交易信号。"
    ok, detail = adapter.send_message(message)
    print(f"测试消息：{ok} {detail}")
    if place_call:
        ok, detail = adapter.voice_call()
        print(f"测试通话：{ok} {detail}")
    return 0


def run(settings: Settings) -> int:
    service = MonitorService(settings)
    service.start()
    print("监控运行中，按 Ctrl+C 停止。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("正在停止…")
    finally:
        service.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="微信美股/期权交易动作告警")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="只读检查微信、群、成员和联系人")
    probe_parser = sub.add_parser("probe", help="只读捕获目标成员消息元数据")
    probe_parser.add_argument("--seconds", type=int, default=120)
    classify = sub.add_parser("test-classify", help="测试 DeepSeek 交易信号判定")
    classify.add_argument("text")
    alert = sub.add_parser("test-alert", help="测试接警消息；需显式参数才测试通话")
    alert.add_argument("--call", action="store_true")
    sub.add_parser("run", help="启动实时监控")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        settings = Settings.load()
        setup_logging(settings.log_level, settings.project_dir)
        args = build_parser().parse_args(argv)
        if args.command == "doctor":
            return doctor(settings)
        if args.command == "probe":
            return probe(settings, args.seconds)
        if args.command == "test-classify":
            return test_classify(settings, args.text)
        if args.command == "test-alert":
            return test_alert(settings, args.call)
        if args.command == "run":
            return run(settings)
        return 2
    except Exception as exc:
        logging.getLogger(__name__).exception("命令失败")
        print(f"错误：{exc}", file=sys.stderr)
        return 1
