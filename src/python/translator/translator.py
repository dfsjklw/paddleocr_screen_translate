"""
translator/translator.py — 翻译模块

通过 llama.cpp HTTP API 进行翻译，支持并行请求。
TranslatorBackend 抽象基类支持未来添加其他翻译服务。
"""
import requests
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from ..config.settings import TranslatorConfig, AppConfig

# llama.cpp /v1/chat/completions 的请求格式
#_TRANSLATE_PROMPT_ZH = "将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：{text}"
_TRANSLATE_PROMPT_ZH = "将以下英语翻译成中文,非英语部分原文输出：\n{text}"
#_TRANSLATE_PROMPT_XX = "Translate the following text into {target}. Output ONLY the translation, nothing else:\n\n{text}"
_TRANSLATE_PROMPT_XX = "{text}"


@dataclass
class TranslationResult:
    text: str
    original: str
    status: str = "ok"     # ok | error | timeout
    elapsed_ms: float = 0.0
    error_msg: str = ""


class TranslatorBackend(ABC):
    """翻译后端抽象基类"""

    @abstractmethod
    def translate_one(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        ...

    def translate_batch(
        self, texts: list[str], source_lang: str, target_lang: str, parallel: int = 4
    ) -> list[TranslationResult]:
        """并行翻译多条文本"""
        results: list[TranslationResult] = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            future_to_idx = {
                executor.submit(self.translate_one, t, source_lang, target_lang): i
                for i, t in enumerate(texts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = TranslationResult(
                        text=texts[idx], original=texts[idx],
                        status="error", error_msg=str(e),
                    )
        return results


class LlamaCppTranslator(TranslatorBackend):
    """
    llama.cpp HTTP API 翻译后端
    使用 OpenAI 兼容的 /v1/chat/completions 接口
    """

    def __init__(self, config: TranslatorConfig, app_config: AppConfig):
        self._url = config.llama.url.rstrip("/") + "/v1/chat/completions"
        self._timeout = config.llama.timeout
        self._max_retries = config.llama.max_retries
        self._params = config.llama.inference_params
        self._target_lang = app_config.target_lang

    def _build_prompt(self, text: str, target_lang: str) -> str:
        if target_lang in ("zh", "中文", "Chinese", "chinese"):
            return _TRANSLATE_PROMPT_ZH.format(text=text)
        return _TRANSLATE_PROMPT_XX.format(target=target_lang, text=text)

    def translate_one(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        if not text.strip():
            return TranslationResult(text="", original=text, status="ok")

        prompt = self._build_prompt(text, target_lang)
        payload = {
            "messages": [
                {"role": "system", "content": ""},
                #{"role": "system", "content": "You are a professional translator. Output only the translation."},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._params.get("temperature", 0.7),
            "top_k": self._params.get("top_k", 20),
            "top_p": self._params.get("top_p", 0.6),
            "repeat_penalty": self._params.get("repeat_penalty", 1.05),
            "n_predict": self._params.get("n_predict", 512),
            "stream": False,
        }

        t0 = time.perf_counter()
        last_err = ""

        for attempt in range(self._max_retries + 1):
            try:
                resp = requests.post(
                    self._url, json=payload,
                    timeout=(5, self._timeout),  # (connect, read)
                )
                resp.raise_for_status()
                data = resp.json()

                # 解析 OpenAI 兼容格式
                content = data["choices"][0]["message"]["content"].strip()
                elapsed = (time.perf_counter() - t0) * 1000
                return TranslationResult(
                    text=content, original=text,
                    status="ok", elapsed_ms=elapsed,
                )

            except requests.exceptions.Timeout:
                last_err = "timeout"
            except requests.exceptions.ConnectionError:
                last_err = "connection_error"
            except Exception as e:
                last_err = str(e)

            # 指数退避重试
            if attempt < self._max_retries:
                time.sleep(2 ** attempt)  # 1s, 2s

        elapsed = (time.perf_counter() - t0) * 1000
        return TranslationResult(
            text=text, original=text,
            status="error", elapsed_ms=elapsed,
            error_msg=last_err,
        )


def create_translator(config: AppConfig) -> TranslatorBackend:
    """工厂函数：根据配置创建翻译后端"""
    backend = config.translator.backend
    if backend == "llama":
        return LlamaCppTranslator(config.translator, config)
    raise ValueError(f"Unknown translator backend: {backend}")
