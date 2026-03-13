"""LLM 客户端抽象层，支持 OpenAI / Anthropic / Ollama / 通义千问"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .config import LLMConfig

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]]) -> str:
        ...

    def chat_with_structured_output(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        response = self.chat(messages)
        return self._extract_json(response)

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                if len(parsed) == 1 and isinstance(parsed[0], dict):
                    return parsed[0]
                return {"items": parsed}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end > start:
                try:
                    items = json.loads(text[start:end])
                    if isinstance(items, list) and items:
                        return items[0] if len(items) == 1 else {"items": items}
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse structured LLM output, returning raw text")
            return {"raw_text": text}


class OpenAIClient(BaseLLMClient):
    def chat(self, messages: List[Dict[str, str]]) -> str:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=self.config.model,
            api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        response = llm.invoke(messages)
        return str(response.content)


class AnthropicClient(BaseLLMClient):
    def chat(self, messages: List[Dict[str, str]]) -> str:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=self.config.model,
            api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        response = llm.invoke(messages)
        return str(response.content)


class OllamaClient(BaseLLMClient):
    def chat(self, messages: List[Dict[str, str]]) -> str:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.config.ollama_endpoint}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "")
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(
                f"Ollama request failed ({self.config.ollama_endpoint}): {e}"
            ) from e


class TongyiClient(BaseLLMClient):
    def chat(self, messages: List[Dict[str, str]]) -> str:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "model": self.config.model or "qwen-turbo",
            "input": {"messages": messages},
            "parameters": {"temperature": self.config.temperature},
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.tongyi_api_key or self.config.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("output", {}).get("text", "")
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"Tongyi API request failed: {e}") from e


class LLMClientFactory:
    _clients: Dict[str, type] = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
        "ollama": OllamaClient,
        "tongyi": TongyiClient,
    }

    @classmethod
    def get_client(cls, config: LLMConfig) -> BaseLLMClient:
        client_cls = cls._clients.get(config.provider)
        if not client_cls:
            raise ValueError(f"Unsupported LLM provider: {config.provider}. "
                             f"Supported: {list(cls._clients.keys())}")
        return client_cls(config)
