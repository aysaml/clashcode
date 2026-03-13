"""模型选择器 - 为红蓝对抗三智能体随机分配不同模型

支持三种模式:
1. fixed   - 所有智能体使用用户配置的同一模型（默认行为）
2. random  - 从用户配置的候选模型列表中随机选取，每个智能体使用不同模型
3. assign  - 用户为每个智能体手动指定 provider/model
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .config import LLMConfig
from .llm import BaseLLMClient, LLMClientFactory

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    RED_TEAM = "red_team"
    ARBITRATOR = "arbitrator"
    BLUE_TEAM = "blue_team"


class ModelSelectionStrategy(Enum):
    FIXED = "fixed"
    RANDOM = "random"
    ASSIGN = "assign"


@dataclass
class ModelAssignment:
    role: AgentRole
    model_id: str
    model_name: str
    source: str  # "user_config" | "random_pool" | "manual_assign"


@dataclass
class ModelSelectionConfig:
    strategy: ModelSelectionStrategy = ModelSelectionStrategy.FIXED
    assigned_models: Dict[str, str] = field(default_factory=dict)
    prefer_different_vendors: bool = True
    excluded_models: List[str] = field(default_factory=list)
    candidate_models: List[Dict[str, str]] = field(default_factory=list)


class ModelSelector:
    """为红蓝对抗三智能体选择/分配模型

    random 模式下，从 config 中的 candidate_models 列表随机选取。
    candidate_models 格式: [{"provider": "openai", "model": "gpt-4o"}, ...]
    """

    def __init__(
        self,
        user_llm_config: LLMConfig,
        selection_config: ModelSelectionConfig,
    ):
        self.user_llm_config = user_llm_config
        self.selection_config = selection_config
        self._assignments: Dict[AgentRole, ModelAssignment] = {}

    def select_models(self) -> Dict[AgentRole, ModelAssignment]:
        strategy = self.selection_config.strategy

        if strategy == ModelSelectionStrategy.FIXED:
            self._assignments = self._assign_fixed()
        elif strategy == ModelSelectionStrategy.RANDOM:
            self._assignments = self._assign_random()
        elif strategy == ModelSelectionStrategy.ASSIGN:
            self._assignments = self._assign_manual()
        else:
            self._assignments = self._assign_fixed()

        self._log_assignments()
        return self._assignments

    def get_client_for_role(self, role: AgentRole) -> BaseLLMClient:
        assignment = self._assignments.get(role)
        if not assignment:
            self.select_models()
            assignment = self._assignments.get(role)

        if not assignment or assignment.source == "user_config":
            return LLMClientFactory.get_client(self.user_llm_config)

        config = self._build_config_for_assignment(assignment)
        return LLMClientFactory.get_client(config)

    def get_assignments(self) -> Dict[AgentRole, ModelAssignment]:
        return dict(self._assignments)

    def get_assignment_summary(self) -> str:
        if not self._assignments:
            return "模型尚未分配"
        lines = ["**智能体模型分配:**"]
        role_names = {
            AgentRole.RED_TEAM: "红队(攻击)",
            AgentRole.ARBITRATOR: "仲裁(验证)",
            AgentRole.BLUE_TEAM: "蓝队(修复)",
        }
        for role in [AgentRole.RED_TEAM, AgentRole.ARBITRATOR, AgentRole.BLUE_TEAM]:
            a = self._assignments.get(role)
            if a:
                lines.append(f"- {role_names[role]}: `{a.model_name}` ({a.source})")
        return "\n".join(lines)

    def _assign_fixed(self) -> Dict[AgentRole, ModelAssignment]:
        model_name = f"{self.user_llm_config.provider}/{self.user_llm_config.model}"
        return {
            role: ModelAssignment(
                role=role,
                model_id=self.user_llm_config.model,
                model_name=model_name,
                source="user_config",
            )
            for role in AgentRole
        }

    def _assign_random(self) -> Dict[AgentRole, ModelAssignment]:
        candidates = self.selection_config.candidate_models
        excluded = set(self.selection_config.excluded_models)
        candidates = [c for c in candidates if c.get("model", "") not in excluded]

        if len(candidates) < 1:
            logger.warning("No candidate models for random selection, falling back to fixed")
            return self._assign_fixed()

        roles = [AgentRole.RED_TEAM, AgentRole.ARBITRATOR, AgentRole.BLUE_TEAM]
        assignments: Dict[AgentRole, ModelAssignment] = {}

        if self.selection_config.prefer_different_vendors and len(candidates) >= 2:
            selected = self._pick_diverse(candidates, len(roles))
        else:
            selected = random.sample(candidates, min(len(roles), len(candidates)))
            while len(selected) < len(roles):
                selected.append(random.choice(candidates))

        random.shuffle(selected)

        for role, model_cfg in zip(roles, selected):
            provider = model_cfg.get("provider", self.user_llm_config.provider)
            model = model_cfg.get("model", self.user_llm_config.model)
            assignments[role] = ModelAssignment(
                role=role,
                model_id=model,
                model_name=f"{provider}/{model}",
                source="random_pool",
            )

        return assignments

    def _assign_manual(self) -> Dict[AgentRole, ModelAssignment]:
        assigned = self.selection_config.assigned_models
        assignments: Dict[AgentRole, ModelAssignment] = {}

        for role in AgentRole:
            spec = assigned.get(role.value, "")
            if spec and "/" in spec:
                provider, model = spec.split("/", 1)
                assignments[role] = ModelAssignment(
                    role=role,
                    model_id=model,
                    model_name=spec,
                    source="manual_assign",
                )
            elif spec:
                assignments[role] = ModelAssignment(
                    role=role,
                    model_id=spec,
                    model_name=f"{self.user_llm_config.provider}/{spec}",
                    source="manual_assign",
                )
            else:
                assignments[role] = ModelAssignment(
                    role=role,
                    model_id=self.user_llm_config.model,
                    model_name=f"{self.user_llm_config.provider}/{self.user_llm_config.model}",
                    source="user_config",
                )

        return assignments

    def _pick_diverse(
        self, candidates: List[Dict[str, str]], count: int
    ) -> List[Dict[str, str]]:
        by_vendor: Dict[str, List[Dict[str, str]]] = {}
        for c in candidates:
            vendor = c.get("provider", "unknown")
            by_vendor.setdefault(vendor, []).append(c)

        selected: List[Dict[str, str]] = []
        vendors = list(by_vendor.keys())
        random.shuffle(vendors)

        vendor_idx = 0
        while len(selected) < count:
            vendor = vendors[vendor_idx % len(vendors)]
            pool = by_vendor[vendor]
            remaining = [m for m in pool if m not in selected]
            if remaining:
                selected.append(random.choice(remaining))
            else:
                selected.append(random.choice(pool))
            vendor_idx += 1

        return selected

    def _build_config_for_assignment(self, assignment: ModelAssignment) -> LLMConfig:
        parts = assignment.model_name.split("/", 1)
        provider = parts[0] if len(parts) == 2 else self.user_llm_config.provider
        model = parts[1] if len(parts) == 2 else assignment.model_id

        return LLMConfig(
            provider=provider,
            api_key=self.user_llm_config.api_key,
            model=model,
            temperature=self.user_llm_config.temperature,
            max_tokens=self.user_llm_config.max_tokens,
            ollama_endpoint=self.user_llm_config.ollama_endpoint,
            tongyi_api_key=self.user_llm_config.tongyi_api_key,
        )

    def _log_assignments(self) -> None:
        for role, assignment in self._assignments.items():
            logger.info(
                f"Model assigned: {role.value} -> {assignment.model_name} ({assignment.source})"
            )
