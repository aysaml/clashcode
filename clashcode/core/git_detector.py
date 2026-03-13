"""Git 变更识别模块 - 基于原生 Git 命令实现暂存区/提交/单文件变更识别"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from .factory import AdapterFactory
from .models import ChangeType, FileChange

logger = logging.getLogger(__name__)


class GitChangeDetector:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._verify_git_repo()

    def _verify_git_repo(self) -> None:
        try:
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(f"'{self.project_root}' is not a git repository")

    def get_staged_changes(self) -> List[FileChange]:
        return self._get_changes("--cached")

    def get_committed_changes(self, ref: str = "HEAD~1") -> List[FileChange]:
        return self._get_changes(f"{ref} HEAD")

    def get_working_changes(self) -> List[FileChange]:
        return self._get_changes("")

    def get_file_changes(
        self, file_path: str, selected_code: Optional[str] = None
    ) -> List[FileChange]:
        full_path = self.project_root / file_path
        if not full_path.exists():
            logger.warning(f"File not found: {full_path}")
            return []

        content = selected_code or full_path.read_text(encoding="utf-8")

        fc = FileChange(
            file_path=str(full_path),
            change_type=ChangeType.MODIFIED,
            new_content=content,
        )

        lang = AdapterFactory.detect_language(file_path)
        if lang:
            adapter = AdapterFactory.get_adapter(lang)
            fc.changed_functions = adapter.extract_changed_functions(fc)

        return [fc]

    def _get_changes(self, diff_args: str) -> List[FileChange]:
        file_changes: List[FileChange] = []
        try:
            cmd = f"git diff --name-status {diff_args}".strip()
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
            )
            if not result.stdout.strip():
                return []

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    continue
                status_char, file_path = parts[0].strip(), parts[1].strip()

                # Handle rename status (R100 old_path new_path)
                if status_char.startswith("R"):
                    status_char = "M"
                    path_parts = file_path.split("\t")
                    file_path = path_parts[-1] if path_parts else file_path

                try:
                    change_type = ChangeType(status_char[0])
                except ValueError:
                    change_type = ChangeType.MODIFIED

                old_content = self._get_file_content_from_git(file_path, diff_args, "old")
                new_content = (
                    self._get_file_content_from_git(file_path, diff_args, "new")
                    if change_type != ChangeType.DELETED
                    else None
                )

                fc = FileChange(
                    file_path=str(self.project_root / file_path),
                    change_type=change_type,
                    old_content=old_content,
                    new_content=new_content,
                )

                if change_type != ChangeType.DELETED and new_content:
                    lang = AdapterFactory.detect_language(file_path)
                    if lang:
                        adapter = AdapterFactory.get_adapter(lang)
                        fc.changed_functions = adapter.extract_changed_functions(fc)

                file_changes.append(fc)

        except subprocess.CalledProcessError as e:
            logger.error(f"Git diff failed: {e.stderr}")
            raise RuntimeError(f"Git command failed: {e.stderr}")

        return file_changes

    def _get_file_content_from_git(
        self, file_path: str, diff_args: str, version: str
    ) -> Optional[str]:
        try:
            if version == "old" and diff_args:
                parts = diff_args.strip().split()
                ref = parts[0] if parts and not parts[0].startswith("--") else "HEAD"
                cmd = f"git show {ref}:{file_path}"
            elif version == "new":
                if "--cached" in diff_args:
                    cmd = f"git show :{file_path}"
                else:
                    full_path = self.project_root / file_path
                    if full_path.exists():
                        return full_path.read_text(encoding="utf-8")
                    return None
            else:
                full_path = self.project_root / file_path
                if full_path.exists():
                    return full_path.read_text(encoding="utf-8")
                return None

            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return None

    def get_diff_text(self, diff_args: str = "--cached") -> str:
        try:
            result = subprocess.run(
                f"git diff {diff_args}".strip(),
                cwd=self.project_root,
                shell=True,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""
