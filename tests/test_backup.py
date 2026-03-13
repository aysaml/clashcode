"""backup.py 单元测试"""

import pytest
from pathlib import Path
from clashcode.core.backup import BackupManager, BackupConfig


@pytest.fixture
def backup_env(tmp_path: Path):
    """创建测试环境"""
    config = BackupConfig(auto_backup=True, backup_dir=".clashcode_backups", max_backups=3)
    manager = BackupManager(tmp_path, config)

    test_file = tmp_path / "test.py"
    test_file.write_text("original content")

    return manager, test_file, tmp_path


class TestBackupManager:
    def test_backup_creates_file(self, backup_env):
        manager, test_file, root = backup_env
        record = manager.backup(test_file)

        assert record is not None
        assert record.backup_path.exists()
        assert record.backup_path.read_text() == "original content"

    def test_backup_directory_created(self, backup_env):
        manager, test_file, root = backup_env
        backup_dir = root / ".clashcode_backups"
        assert not backup_dir.exists()

        manager.backup(test_file)
        assert backup_dir.exists()

    def test_rollback_restores_content(self, backup_env):
        manager, test_file, root = backup_env
        manager.backup(test_file)

        # Modify file
        test_file.write_text("modified content")
        assert test_file.read_text() == "modified content"

        # Rollback
        success = manager.rollback(test_file)
        assert success is True
        assert test_file.read_text() == "original content"

    def test_rollback_no_backup(self, backup_env):
        manager, _, root = backup_env
        other_file = root / "other.py"
        other_file.write_text("other")

        success = manager.rollback(other_file)
        assert success is False

    def test_backup_disabled(self, tmp_path: Path):
        config = BackupConfig(auto_backup=False)
        manager = BackupManager(tmp_path, config)

        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        record = manager.backup(test_file)
        assert record is None

    def test_cleanup_old_backups(self, backup_env):
        manager, test_file, root = backup_env

        # Create 5 backups (max is 3)
        for i in range(5):
            test_file.write_text(f"version {i}")
            manager.backup(test_file)

        backup_dir = root / ".clashcode_backups"
        backups = list(backup_dir.iterdir())
        assert len(backups) <= 3

    def test_get_backup_diff(self, backup_env):
        manager, test_file, root = backup_env
        manager.backup(test_file)

        test_file.write_text("new content")

        diff = manager.get_backup_diff(test_file)
        assert diff is not None
        old, new = diff
        assert old == "original content"
        assert new == "new content"

    def test_list_backups(self, backup_env):
        manager, test_file, root = backup_env
        assert len(manager.list_backups()) == 0

        manager.backup(test_file)
        assert len(manager.list_backups()) == 1

        test_file.write_text("v2")
        manager.backup(test_file)
        assert len(manager.list_backups()) == 2

    def test_backup_nonexistent_file(self, backup_env):
        manager, _, root = backup_env
        fake = root / "nonexistent.py"
        record = manager.backup(fake)
        assert record is None
