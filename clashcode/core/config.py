"""全局 + 项目级配置管理，YAML 格式"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .models import Severity

DEFAULT_CONFIG_NAME = ".clashcode.yml"


@dataclass
class LLMConfig:
    provider: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4096
    ollama_endpoint: str = "http://localhost:11434"
    tongyi_api_key: str = ""


@dataclass
class AnalysisConfig:
    severity_threshold: Severity = Severity.LOW
    max_dependency_depth: int = 3
    adversarial_rounds: int = 2
    target_language: Optional[str] = None
    focus_scenarios: list[str] = field(default_factory=list)
    model_selection_strategy: str = "fixed"  # fixed / random / assign
    prefer_different_vendors: bool = True
    assigned_models: dict[str, str] = field(default_factory=dict)
    excluded_models: list[str] = field(default_factory=list)
    candidate_models: list[dict[str, str]] = field(default_factory=list)


@dataclass
class BackupConfig:
    auto_backup: bool = True
    backup_dir: str = ".clashcode_backups"
    max_backups: int = 10


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)

    @classmethod
    def load(cls, project_root: Optional[Path] = None) -> Config:
        config = cls()
        home_config = Path.home() / DEFAULT_CONFIG_NAME
        if home_config.exists():
            config._merge_from_file(home_config)
        if project_root:
            project_config = project_root / DEFAULT_CONFIG_NAME
            if project_config.exists():
                config._merge_from_file(project_config)
        return config

    def _merge_from_file(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "llm" in data:
            for k, v in data["llm"].items():
                if hasattr(self.llm, k):
                    setattr(self.llm, k, v)
        if "analysis" in data:
            for k, v in data["analysis"].items():
                if k == "severity_threshold":
                    try:
                        setattr(self.analysis, k, Severity(v))
                    except ValueError:
                        pass  # keep default on invalid value
                elif hasattr(self.analysis, k):
                    setattr(self.analysis, k, v)
        if "backup" in data:
            for k, v in data["backup"].items():
                if hasattr(self.backup, k):
                    setattr(self.backup, k, v)

    def save(self, path: Path) -> None:
        data = {
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "ollama_endpoint": self.llm.ollama_endpoint,
            },
            "analysis": {
                "severity_threshold": self.analysis.severity_threshold.value,
                "max_dependency_depth": self.analysis.max_dependency_depth,
                "adversarial_rounds": self.analysis.adversarial_rounds,
                "target_language": self.analysis.target_language,
                "focus_scenarios": self.analysis.focus_scenarios,
                "model_selection_strategy": self.analysis.model_selection_strategy,
                "prefer_different_vendors": self.analysis.prefer_different_vendors,
                "assigned_models": self.analysis.assigned_models,
                "excluded_models": self.analysis.excluded_models,
                "candidate_models": self.analysis.candidate_models,
            },
            "backup": {
                "auto_backup": self.backup.auto_backup,
                "backup_dir": self.backup.backup_dir,
                "max_backups": self.backup.max_backups,
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
