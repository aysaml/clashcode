"""config.py 单元测试"""

import pytest
from pathlib import Path
from clashcode.core.config import Config, LLMConfig, AnalysisConfig, BackupConfig
from clashcode.core.models import Severity


class TestConfig:
    def test_default_values(self):
        cfg = Config()
        assert cfg.llm.provider == "openai"
        assert cfg.llm.model == "gpt-4o"
        assert cfg.llm.temperature == 0.1
        assert cfg.analysis.severity_threshold == Severity.LOW
        assert cfg.analysis.max_dependency_depth == 3
        assert cfg.analysis.adversarial_rounds == 2
        assert cfg.backup.auto_backup is True
        assert cfg.backup.backup_dir == ".clashcode_backups"
        assert cfg.backup.max_backups == 10

    def test_save_and_load(self, tmp_path: Path):
        cfg = Config()
        cfg.llm.provider = "anthropic"
        cfg.llm.model = "claude-3-opus"
        cfg.analysis.adversarial_rounds = 3
        cfg.backup.max_backups = 5

        config_path = tmp_path / ".clashcode.yml"
        cfg.save(config_path)

        assert config_path.exists()

        loaded = Config.load(tmp_path)
        assert loaded.llm.provider == "anthropic"
        assert loaded.llm.model == "claude-3-opus"
        assert loaded.analysis.adversarial_rounds == 3
        assert loaded.backup.max_backups == 5

    def test_load_nonexistent(self, tmp_path: Path):
        cfg = Config.load(tmp_path)
        assert cfg.llm.provider == "openai"

    def test_merge_partial_config(self, tmp_path: Path):
        import yaml
        partial = {"llm": {"provider": "ollama"}}
        config_path = tmp_path / ".clashcode.yml"
        with open(config_path, "w") as f:
            yaml.dump(partial, f)

        cfg = Config.load(tmp_path)
        assert cfg.llm.provider == "ollama"
        assert cfg.llm.model == "gpt-4o"  # Default preserved
