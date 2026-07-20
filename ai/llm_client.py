"""
LLM API 统一封装 —— 通义千问（阿里云百炼）

提供统一的 LLM 调用接口，所有 AI 模块（NL2SQL、Agent、Insights）通过此模块访问大模型。
支持同步调用与 SSE 流式输出，内置超时、重试处理。

使用方式：
    from ai.llm_client import get_llm_client

    llm = get_llm_client()

    # 同步调用
    answer = llm.chat("你好")

    # 流式调用
    for chunk in llm.chat_stream("讲一个故事"):
        print(chunk, end="")

环境变量（参见 .env）：
    QWEN_API_KEY   — 百炼 API Key（必填）
    QWEN_BASE_URL  — API 地址（可选，默认国内百炼地址）
    LLM_MODEL      — 模型名称（可选，默认 qwen-plus）
"""

import os
import time
import logging
from pathlib import Path
from typing import Iterator, Optional

# 自动加载项目根目录的 .env 文件
try:
    from dotenv import load_dotenv

    _env_file = Path(__file__).resolve().parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

from openai import OpenAI

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"

# 可选模型
MODEL_OPTIONS = {
    "qwen-max":   "通义千问-Max（最强推理，适合复杂 NL2SQL 与报告生成）",
    "qwen-plus":  "通义千问-Plus（性能与成本平衡，推荐默认使用）",
    "qwen-turbo": "通义千问-Turbo（速度最快，适合简单对话与 Agent 调度）",
}

# 调用参数
DEFAULT_TEMPERATURE = 0.1   # NL2SQL 场景需要低温度保证输出稳定
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT = 30        # 秒
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5         # 指数退避基数


# ============================================================
# LLMClient
# ============================================================

class LLMClient:
    """通义千问 LLM 客户端（OpenAI 兼容协议）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key or os.getenv("QWEN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "QWEN_API_KEY not found. "
                "Set env var QWEN_API_KEY or pass api_key parameter.\n"
                "Get Key: https://bailian.console.aliyun.com/?tab=apiKey"
            )

        self.base_url = base_url or os.getenv("QWEN_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

        logger.info(
            "LLMClient init: model=%s, base_url=%s",
            self.model, self.base_url,
        )

    # --------------------------------------------------------
    # 同步调用
    # --------------------------------------------------------

    def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """发送 prompt 到 LLM，返回完整响应文本。"""
        messages = self._build_messages(prompt, system_prompt)
        return self._call_with_retry(messages, temperature, max_tokens)

    # --------------------------------------------------------
    # 流式调用 → 供 C 的 /api/chat SSE 使用
    # --------------------------------------------------------

    def chat_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """流式调用 LLM，逐 token 返回文本块。"""
        messages = self._build_messages(prompt, system_prompt)

        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                stream = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature or self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return

            except Exception as e:
                last_exception = e
                logger.warning(
                    "LLM stream failed (attempt %d/%d): %s",
                    attempt + 1, MAX_RETRIES, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)

        raise RuntimeError(
            f"LLM stream failed after {MAX_RETRIES} retries. "
            f"Last error: {last_exception}"
        )

    # --------------------------------------------------------
    # 内部方法
    # --------------------------------------------------------

    def _build_messages(self, prompt: str, system_prompt: str) -> list[dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _call_with_retry(
        self,
        messages: list[dict],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> str:
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature or self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                    stream=False,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise RuntimeError("LLM returned empty content")
                return content.strip()

            except Exception as e:
                last_exception = e
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1, MAX_RETRIES, e,
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)

        raise RuntimeError(
            f"LLM call failed after {MAX_RETRIES} retries. "
            f"Last error: {last_exception}"
        )

    def switch_model(self, model: str):
        """运行时切换模型（如从 turbo 切到 max 做复杂推理）"""
        self.model = model
        logger.info("Switched to model: %s", model)


# ============================================================
# 全局单例
# ============================================================

_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """获取全局 LLMClient 单例（延迟初始化）"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


# 便捷函数
def chat(prompt: str, system_prompt: str = "") -> str:
    """快捷同步调用"""
    return get_llm_client().chat(prompt, system_prompt)


def chat_stream(prompt: str, system_prompt: str = "") -> Iterator[str]:
    """快捷流式调用"""
    return get_llm_client().chat_stream(prompt, system_prompt)


# ============================================================
# 自检入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    print("=" * 60)
    print("Qwen LLM Client - Self Check")
    has_key = bool(os.getenv("QWEN_API_KEY"))
    print(f"  API Key : {'[OK] configured' if has_key else '[!!] NOT SET'}")
    print(f"  Model   : {os.getenv('LLM_MODEL', DEFAULT_MODEL)}")
    print(f"  Base URL: {os.getenv('QWEN_BASE_URL', DEFAULT_BASE_URL)}")
    print("=" * 60)

    if not has_key:
        print("\nSet env var: QWEN_API_KEY")
        print("Get Key: https://bailian.console.aliyun.com/?tab=apiKey")
    else:
        print("\nTesting API call...")
        try:
            result = chat("请用一句话介绍你自己")
            print(f"[OK] Call succeeded!\nResponse: {result}")
        except Exception as e:
            print(f"[FAIL] Call failed: {e}")
