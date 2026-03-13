"""git_detector.py 单元测试"""

import subprocess
import pytest
from pathlib import Path
from clashcode.core.git_detector import GitChangeDetector
from clashcode.core.models import ChangeType


@pytest.fixture
def git_repo(tmp_path: Path):
    """创建一个临时 Git 仓库用于测试"""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

    # Create initial file and commit
    test_file = tmp_path / "hello.py"
    test_file.write_text("def hello():\n    print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True, check=True)

    return tmp_path


class TestGitChangeDetector:
    def test_init_valid_repo(self, git_repo: Path):
        detector = GitChangeDetector(git_repo)
        assert detector.project_root == git_repo

    def test_init_invalid_repo(self, tmp_path: Path):
        with pytest.raises(RuntimeError, match="not a git repository"):
            GitChangeDetector(tmp_path)

    def test_get_staged_changes(self, git_repo: Path):
        # Modify file and stage
        test_file = git_repo / "hello.py"
        test_file.write_text("def hello():\n    print('world')\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)

        detector = GitChangeDetector(git_repo)
        changes = detector.get_staged_changes()

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.MODIFIED
        assert "hello.py" in changes[0].file_path

    def test_get_staged_no_changes(self, git_repo: Path):
        detector = GitChangeDetector(git_repo)
        changes = detector.get_staged_changes()
        assert len(changes) == 0

    def test_get_file_changes(self, git_repo: Path):
        test_file = git_repo / "hello.py"
        detector = GitChangeDetector(git_repo)
        changes = detector.get_file_changes("hello.py")

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.MODIFIED
        assert "hello" in changes[0].changed_functions

    def test_get_file_changes_with_selected_code(self, git_repo: Path):
        detector = GitChangeDetector(git_repo)
        code = "def new_func():\n    return 42\n"
        changes = detector.get_file_changes("hello.py", selected_code=code)

        assert len(changes) == 1
        assert changes[0].new_content == code
        assert "new_func" in changes[0].changed_functions

    def test_get_file_not_found(self, git_repo: Path):
        detector = GitChangeDetector(git_repo)
        changes = detector.get_file_changes("nonexistent.py")
        assert len(changes) == 0

    def test_committed_changes(self, git_repo: Path):
        # Make a new commit
        new_file = git_repo / "new_module.py"
        new_file.write_text("class Foo:\n    pass\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add module"], cwd=git_repo, capture_output=True, check=True)

        detector = GitChangeDetector(git_repo)
        changes = detector.get_committed_changes("HEAD~1")

        assert len(changes) >= 1
        added = [c for c in changes if "new_module" in c.file_path]
        assert len(added) == 1

    def test_extract_functions_from_staged(self, git_repo: Path):
        code = "def foo():\n    pass\n\ndef bar():\n    pass\n\nclass Baz:\n    pass\n"
        test_file = git_repo / "funcs.py"
        test_file.write_text(code)
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)

        detector = GitChangeDetector(git_repo)
        changes = detector.get_staged_changes()

        added = [c for c in changes if "funcs.py" in c.file_path]
        assert len(added) == 1
        assert "foo" in added[0].changed_functions
        assert "bar" in added[0].changed_functions
        assert "Baz" in added[0].changed_functions
