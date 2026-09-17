from __future__ import annotations

import json
import logging
import time

from .config import Settings
from .models import TradeSignal

LOG = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是美股交易指令分类器。输入只包含同一位指定发言人在短时间内按时间顺序发送的消息。
识别美股股票或美股期权的明确交易动作：买入、卖出、做空、回补、加仓、减仓、开仓、平仓、滚仓、行权、撤单。
以下不是交易信号：提问、行情讨论、新闻、复盘过去行为、假设、引用他人、纯观点、仅说持有不动。
交易指令可能拆成连续多条消息。必须把 recent_target_messages 与 current_message 合并理解，例如：
- 上一条“aapl 9/18 325p”，当前“买9.25的”表示买入 AAPL 9/18 325 Put，价格 9.25。
- 上一条“买”，当前补充合约或股票代码时，只要合并后已形成明确指令，也属于交易信号。
- “meta可以开始止盈”是明确的减仓/平仓信号。
当且仅当 current_message 新增了交易动作，或补全了紧邻上下文中尚不完整的动作，使合并后的指令首次变得可执行时，is_trade_signal 才为 true。
如果上下文在当前消息之前已经是一条完整指令，而当前消息只补充价格、区间或重复说明，不视为新的交易信号，避免重复告警。
标的必须能由当前消息或紧邻上下文确定。期权需尽量抽取 call/put、行权价、到期日和成交/限价；缺失字段用空字符串，不要猜年份。
price 保存价格或价格区间原文。evidence 只拼接与本次信号直接相关的消息，按时间顺序用“ | ”分隔。confidence 是 0 到 1。
你必须只输出一个 JSON 对象，不要 Markdown，不要解释。JSON schema：
{"is_trade_signal":false,"action":"unknown","asset_type":"unknown","symbol":"","option_type":"","strike":"","expiry":"","quantity":"","price":"","urgency":"normal","confidence":0.0,"evidence":"","reason":""}
action 只能是 buy/sell/short/cover/add/reduce/open/close/roll/exercise/cancel/hold/unknown；asset_type 只能是 stock/option/unknown；option_type 只能是 call/put/unknown/空字符串。"""


class DeepSeekDetector:
    def __init__(self, settings: Settings):
        self.settings = settings

    def classify(self, text: str, context: list[str] | None = None) -> TradeSignal:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 未配置")
        prompt = {
            "recent_target_messages": (context or [])[-self.settings.context_messages :],
            "current_message": text,
        }
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 500,
        }
        import requests

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    f"{self.settings.deepseek_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.settings.deepseek_timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                return TradeSignal.from_dict(json.loads(content))
            except Exception as exc:
                last_error = exc
                LOG.warning("DeepSeek 请求第 %d 次失败：%s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"DeepSeek 连续失败：{last_error}")
