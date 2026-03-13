"""model_selector.py 单元测试 - 纯配置驱动，无 IDE 代理依赖"""

import pytest

from clashcode.core.model_selector import (
    AgentRole,
    ModelAssignment,
    ModelSelectionConfig,
    ModelSelectionStrategy,
    ModelSelector,
)
from clashcode.core.config import LLMConfig


CANDIDATE_MODELS = [
    {"provider": "openai", "model": "gpt-4o"},
    {"provider": "anthropic", "model": "claude-3.5-sonnet"},
    {"provider": "ollama", "model": "llama3"},
    {"provider": "tongyi", "model": "qwen-turbo"},
]


@pytest.fixture
def user_config():
    return LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


class TestModelSelectionStrategy:
    def test_enum_values(self):
        assert ModelSelectionStrategy.FIXED.value == "fixed"
        assert ModelSelectionStrategy.RANDOM.value == "random"
        assert ModelSelectionStrategy.ASSIGN.value == "assign"


class TestAgentRole:
    def test_all_roles(self):
        assert AgentRole.RED_TEAM.value == "red_team"
        assert AgentRole.ARBITRATOR.value == "arbitrator"
        assert AgentRole.BLUE_TEAM.value == "blue_team"


class TestModelSelectorFixed:
    def test_fixed_all_same_model(self, user_config):
        sel_config = ModelSelectionConfig(strategy=ModelSelectionStrategy.FIXED)
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        assert len(assignments) == 3
        for role in AgentRole:
            assert assignments[role].source == "user_config"
            assert assignments[role].model_id == "gpt-4o"

    def test_fixed_summary(self, user_config):
        sel_config = ModelSelectionConfig(strategy=ModelSelectionStrategy.FIXED)
        selector = ModelSelector(user_config, sel_config)
        selector.select_models()
        summary = selector.get_assignment_summary()
        assert "红队" in summary
        assert "仲裁" in summary
        assert "蓝队" in summary


class TestModelSelectorRandom:
    def test_random_assigns_from_candidates(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.RANDOM,
            candidate_models=CANDIDATE_MODELS,
            prefer_different_vendors=True,
        )
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        assert len(assignments) == 3
        for role in AgentRole:
            assert assignments[role].source == "random_pool"

        model_ids = {a.model_id for a in assignments.values()}
        assert len(model_ids) >= 2

    def test_random_prefers_different_vendors(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.RANDOM,
            candidate_models=CANDIDATE_MODELS,
            prefer_different_vendors=True,
        )
        selector = ModelSelector(user_config, sel_config)

        vendor_sets = []
        for _ in range(10):
            assignments = selector.select_models()
            vendors = {a.model_name.split("/")[0] for a in assignments.values()}
            vendor_sets.append(len(vendors))

        assert sum(1 for v in vendor_sets if v >= 2) >= 5

    def test_random_fallback_to_fixed_when_no_candidates(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.RANDOM,
            candidate_models=[],
        )
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        for role in AgentRole:
            assert assignments[role].source == "user_config"

    def test_random_with_excluded_models(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.RANDOM,
            candidate_models=CANDIDATE_MODELS,
            excluded_models=["gpt-4o", "llama3"],
        )
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        for a in assignments.values():
            assert a.model_id not in ["gpt-4o", "llama3"]

    def test_random_single_candidate(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.RANDOM,
            candidate_models=[{"provider": "openai", "model": "gpt-4o"}],
        )
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        assert len(assignments) == 3
        for role in AgentRole:
            assert assignments[role].model_id == "gpt-4o"


class TestModelSelectorAssign:
    def test_assign_with_provider_slash_model(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.ASSIGN,
            assigned_models={
                "red_team": "anthropic/claude-3.5-sonnet",
                "arbitrator": "openai/gpt-4o",
                "blue_team": "ollama/llama3",
            },
        )
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        assert assignments[AgentRole.RED_TEAM].model_id == "claude-3.5-sonnet"
        assert assignments[AgentRole.RED_TEAM].model_name == "anthropic/claude-3.5-sonnet"
        assert assignments[AgentRole.ARBITRATOR].model_id == "gpt-4o"
        assert assignments[AgentRole.BLUE_TEAM].model_id == "llama3"

    def test_assign_model_only(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.ASSIGN,
            assigned_models={
                "red_team": "claude-3.5-sonnet",
            },
        )
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        assert assignments[AgentRole.RED_TEAM].source == "manual_assign"
        assert assignments[AgentRole.RED_TEAM].model_name == "openai/claude-3.5-sonnet"

    def test_assign_partial_fallback(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.ASSIGN,
            assigned_models={
                "red_team": "anthropic/claude-3.5-sonnet",
            },
        )
        selector = ModelSelector(user_config, sel_config)
        assignments = selector.select_models()

        assert assignments[AgentRole.RED_TEAM].source == "manual_assign"
        assert assignments[AgentRole.ARBITRATOR].source == "user_config"
        assert assignments[AgentRole.BLUE_TEAM].source == "user_config"


class TestModelSelectorGetClient:
    def test_get_client_for_fixed(self, user_config):
        sel_config = ModelSelectionConfig(strategy=ModelSelectionStrategy.FIXED)
        selector = ModelSelector(user_config, sel_config)
        selector.select_models()

        from clashcode.core.llm import OpenAIClient
        client = selector.get_client_for_role(AgentRole.RED_TEAM)
        assert isinstance(client, OpenAIClient)

    def test_get_client_for_random_pool(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.RANDOM,
            candidate_models=[{"provider": "openai", "model": "gpt-4o-mini"}],
        )
        selector = ModelSelector(user_config, sel_config)
        selector.select_models()

        from clashcode.core.llm import OpenAIClient
        client = selector.get_client_for_role(AgentRole.RED_TEAM)
        assert isinstance(client, OpenAIClient)
        assert client.config.model == "gpt-4o-mini"

    def test_get_client_for_assigned(self, user_config):
        sel_config = ModelSelectionConfig(
            strategy=ModelSelectionStrategy.ASSIGN,
            assigned_models={"red_team": "ollama/llama3"},
        )
        selector = ModelSelector(user_config, sel_config)
        selector.select_models()

        from clashcode.core.llm import OllamaClient
        client = selector.get_client_for_role(AgentRole.RED_TEAM)
        assert isinstance(client, OllamaClient)
        assert client.config.model == "llama3"
