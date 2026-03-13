"""impact_analyzer.py 单元测试"""

import pytest
from pathlib import Path
from clashcode.core.impact_analyzer import ImpactAnalyzer
from clashcode.core.config import AnalysisConfig
from clashcode.core.models import ChangeType, FileChange, Severity


@pytest.fixture
def python_project(tmp_path: Path):
    """创建简单 Python 项目结构"""
    (tmp_path / "main.py").write_text(
        "from utils import helper\n\ndef main():\n    helper()\n"
    )
    (tmp_path / "utils.py").write_text(
        "def helper():\n    return 42\n"
    )
    (tmp_path / "api.py").write_text(
        "from utils import helper\n\ndef get_data():\n    return helper()\n"
    )
    return tmp_path


class TestImpactAnalyzer:
    def test_build_graph_with_python_files(self, python_project: Path):
        config = AnalysisConfig(target_language="python")
        analyzer = ImpactAnalyzer(python_project, config)

        changes = [
            FileChange(
                file_path=str(python_project / "utils.py"),
                change_type=ChangeType.MODIFIED,
                new_content="def helper():\n    return 42\n",
                changed_functions=["helper"],
            )
        ]

        graph = analyzer.build_dependency_graph(changes)
        assert len(graph.changed_files) == 1
        assert "utils.py" in graph.changed_files[0]
        # main.py and api.py both import utils
        assert len(graph.impacted_files) >= 1

    def test_mermaid_generation(self, python_project: Path):
        config = AnalysisConfig(target_language="python")
        analyzer = ImpactAnalyzer(python_project, config)

        changes = [
            FileChange(
                file_path=str(python_project / "utils.py"),
                change_type=ChangeType.MODIFIED,
                new_content="def helper():\n    return 42\n",
                changed_functions=["helper"],
            )
        ]

        graph = analyzer.build_dependency_graph(changes)
        assert graph.mermaid_code.startswith("flowchart LR")
        assert "变更文件" in graph.mermaid_code

    def test_cache_mechanism(self, python_project: Path):
        config = AnalysisConfig(target_language="python")
        analyzer = ImpactAnalyzer(python_project, config)

        changes = [
            FileChange(
                file_path=str(python_project / "utils.py"),
                change_type=ChangeType.MODIFIED,
                new_content="def helper():\n    return 42\n",
                changed_functions=["helper"],
            )
        ]

        graph1 = analyzer.build_dependency_graph(changes)
        graph2 = analyzer.build_dependency_graph(changes)
        assert graph1 is graph2  # Same object from cache

    def test_clear_cache(self, python_project: Path):
        config = AnalysisConfig(target_language="python")
        analyzer = ImpactAnalyzer(python_project, config)

        changes = [
            FileChange(
                file_path=str(python_project / "utils.py"),
                change_type=ChangeType.MODIFIED,
                new_content="def helper():\n    return 42\n",
                changed_functions=["helper"],
            )
        ]

        graph1 = analyzer.build_dependency_graph(changes)
        analyzer.clear_cache()
        graph2 = analyzer.build_dependency_graph(changes)
        assert graph1 is not graph2

    def test_no_language_detected(self, tmp_path: Path):
        config = AnalysisConfig()
        analyzer = ImpactAnalyzer(tmp_path, config)

        changes = [
            FileChange(
                file_path=str(tmp_path / "data.txt"),
                change_type=ChangeType.MODIFIED,
            )
        ]

        graph = analyzer.build_dependency_graph(changes)
        assert graph.mermaid_code.startswith("flowchart LR")

    def test_impact_summary(self, python_project: Path):
        config = AnalysisConfig(target_language="python")
        analyzer = ImpactAnalyzer(python_project, config)

        changes = [
            FileChange(
                file_path=str(python_project / "utils.py"),
                change_type=ChangeType.MODIFIED,
                new_content="def helper():\n    return 42\n",
                changed_functions=["helper"],
            )
        ]

        graph = analyzer.build_dependency_graph(changes)
        summary = analyzer.get_impact_summary(graph)
        assert "影响范围概览" in summary
        assert "变更文件: 1" in summary
