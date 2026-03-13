"""llm.py 单元测试"""

import pytest
from clashcode.core.llm import BaseLLMClient, LLMClientFactory, OpenAIClient, OllamaClient
from clashcode.core.config import LLMConfig


class TestLLMClientFactory:
    def test_get_openai_client(self):
        config = LLMConfig(provider="openai", api_key="sk-test")
        client = LLMClientFactory.get_client(config)
        assert isinstance(client, OpenAIClient)

    def test_get_ollama_client(self):
        config = LLMConfig(provider="ollama")
        client = LLMClientFactory.get_client(config)
        assert isinstance(client, OllamaClient)

    def test_unsupported_provider(self):
        config = LLMConfig(provider="invalid")
        with pytest.raises(ValueError, match="Unsupported"):
            LLMClientFactory.get_client(config)


class TestExtractJSON:
    def test_plain_json(self):
        result = BaseLLMClient._extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_markdown(self):
        text = '```json\n{"key": "value"}\n```'
        result = BaseLLMClient._extract_json(text)
        assert result == {"key": "value"}

    def test_json_embedded_in_text(self):
        text = 'Here is the result:\n{"severity": "high", "line": 10}\nEnd.'
        result = BaseLLMClient._extract_json(text)
        assert result["severity"] == "high"

    def test_json_array(self):
        text = '[{"a": 1}, {"b": 2}]'
        result = BaseLLMClient._extract_json(text)
        assert "items" in result
        assert len(result["items"]) == 2

    def test_single_item_array(self):
        text = '[{"line": 5}]'
        result = BaseLLMClient._extract_json(text)
        assert result["line"] == 5

    def test_invalid_json(self):
        result = BaseLLMClient._extract_json("not json at all")
        assert "raw_text" in result
