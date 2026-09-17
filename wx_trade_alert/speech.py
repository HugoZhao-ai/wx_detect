from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings

LOG = logging.getLogger(__name__)
TRADE_VOCABULARY_PROMPT = (
    "这是美股和美股期权交易语音。常见词包括：买入、卖出、做空、回补、"
    "加仓、减仓、开仓、平仓、滚仓、Call、Put、股票代码、到期日、行权价、手。"
)


class SpeechTranscriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            LOG.info(
                "加载 Whisper 模型 %s（%s/%s），首次运行会下载模型…",
                self.settings.whisper_model,
                self.settings.whisper_device,
                self.settings.whisper_compute_type,
            )
            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
                download_root=str(self.settings.data_dir / "models"),
            )
        return self._model

    def transcribe_silk(self, silk_path: str | Path) -> str:
        import numpy as np
        import pysilk

        source = Path(silk_path)
        pcm_path = source.with_suffix(".pcm")
        with source.open("rb") as silk_file, pcm_path.open("wb") as pcm_file:
            pysilk.decode(silk_file, pcm_file, self.settings.silk_sample_rate)
        try:
            pcm = np.fromfile(pcm_path, dtype=np.int16).astype(np.float32) / 32768.0
            if pcm.size == 0:
                raise RuntimeError("SILK 解码后没有音频样本")
            audio = self._resample(pcm, self.settings.silk_sample_rate, 16000)
            model = self._load_model()
            segments, _info = model.transcribe(
                audio,
                language="zh",
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=TRADE_VOCABULARY_PROMPT,
            )
            text = "".join(segment.text for segment in segments).strip()
            if text:
                return text
            LOG.warning("VAD 未检测到语音，关闭 VAD 重试一次")
            segments, _info = model.transcribe(
                audio,
                language="zh",
                beam_size=5,
                vad_filter=False,
                condition_on_previous_text=False,
                initial_prompt=TRADE_VOCABULARY_PROMPT,
            )
            return "".join(segment.text for segment in segments).strip()
        finally:
            pcm_path.unlink(missing_ok=True)

    @staticmethod
    def _resample(samples, source_rate: int, target_rate: int):
        if source_rate == target_rate:
            return samples
        import numpy as np

        target_len = max(1, round(len(samples) * target_rate / source_rate))
        old_x = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
        new_x = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
        return np.interp(new_x, old_x, samples).astype(np.float32)
