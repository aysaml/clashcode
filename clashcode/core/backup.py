"""自动备份与回滚管理 - 修复前自动备份，支持一键回滚"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import BackupConfig

logger = logging.getLogger(__name__)


class BackupRecord:
    def __init__(self, original_path: Path, backup_path: Path, timestamp: str):
        self.original_path = original_path
        self.backup_path = backup_path
        self.timestamp = timestamp


class BackupManager:
    def __init__(self, project_root: Path, config: Optional[BackupConfig] = None):
        self.project_root = project_root
        self.config = config or BackupConfig()
        self.backup_dir = project_root / self.config.backup_dir
        self._records: List[BackupRecord] = []

    def backup(self, file_path: Path) -> Optional[BackupRecord]:
        if not self.config.auto_backup:
            return None

        if not file_path.exists():
            logger.warning(f"Cannot backup: file not found {file_path}")
            return None

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        relative = file_path.relative_to(self.project_root) if file_path.is_relative_to(self.project_root) else file_path

        backup_name = f"{relative.stem}_{timestamp}{relative.suffix}"
        backup_path = self.backup_dir / backup_name

        try:
            shutil.copy2(str(file_path), str(backup_path))
            record = BackupRecord(file_path, backup_path, timestamp)
            self._records.append(record)
            logger.info(f"Backed up {file_path} -> {backup_path}")
            self._cleanup_old_backups(file_path)
            return record
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None

    def rollback(self, file_path: Path) -> bool:
        matching = [
            r for r in reversed(self._records) if r.original_path == file_path
        ]

        if not matching:
            matching_from_disk = self._find_backups_on_disk(file_path)
            if matching_from_disk:
                latest = max(matching_from_disk, key=lambda p: p.stat().st_mtime)
                try:
                    shutil.copy2(str(latest), str(file_path))
                    logger.info(f"Rolled back {file_path} from {latest}")
                    return True
                except Exception as e:
                    logger.error(f"Rollback failed: {e}")
                    return False

            logger.warning(f"No backup found for {file_path}")
            return False

        record = matching[0]
        if not record.backup_path.exists():
            logger.error(f"Backup file missing: {record.backup_path}")
            return False

        try:
            shutil.copy2(str(record.backup_path), str(record.original_path))
            logger.info(f"Rolled back {file_path} from {record.backup_path}")
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def get_latest_backup(self, file_path: Path) -> Optional[Path]:
        matching = [
            r for r in reversed(self._records) if r.original_path == file_path
        ]
        if matching:
            return matching[0].backup_path

        from_disk = self._find_backups_on_disk(file_path)
        if from_disk:
            return max(from_disk, key=lambda p: p.stat().st_mtime)
        return None

    def get_backup_diff(self, file_path: Path) -> Optional[tuple[str, str]]:
        backup = self.get_latest_backup(file_path)
        if not backup or not backup.exists() or not file_path.exists():
            return None
        old_content = backup.read_text(encoding="utf-8")
        new_content = file_path.read_text(encoding="utf-8")
        return (old_content, new_content)

    def list_backups(self) -> List[BackupRecord]:
        return list(self._records)

    def _find_backups_on_disk(self, file_path: Path) -> List[Path]:
        if not self.backup_dir.exists():
            return []
        stem = file_path.stem
        suffix = file_path.suffix
        return [
            p
            for p in self.backup_dir.iterdir()
            if p.name.startswith(stem) and p.name.endswith(suffix) and p.is_file()
        ]

    def _cleanup_old_backups(self, file_path: Path) -> None:
        backups = self._find_backups_on_disk(file_path)
        if len(backups) <= self.config.max_backups:
            return
        backups.sort(key=lambda p: p.stat().st_mtime)
        to_remove = backups[: len(backups) - self.config.max_backups]
        for old_backup in to_remove:
            try:
                old_backup.unlink()
                logger.debug(f"Removed old backup: {old_backup}")
            except Exception as e:
                logger.warning(f"Failed to remove old backup {old_backup}: {e}")
