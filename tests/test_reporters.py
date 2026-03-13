"""reporters.py 单元测试"""

import json
import pytest
from pathlib import Path
from clashcode.core.reporters import MarkdownReporter, JSONReporter, ReporterFactory
from clashcode.core.models import (
    AnalysisResult,
    DependencyGraph,
    FileChange,
    ChangeType,
    FixStrategy,
    Severity,
    Vulnerability,
)


@pytest.fixture
def sample_result():
    return AnalysisResult(
        file_changes=[
            FileChange("src/api.py", ChangeType.MODIFIED, changed_functions=["handle_request"])
        ],
        dependency_graph=DependencyGraph(
            changed_files=["src/api.py"],
            impacted_files=["src/service.py", "src/db.py"],
            dependency_chains=["api.py -> service.py", "api.py -> db.py"],
            mermaid_code="flowchart LR\n    A[api.py] --> B[service.py]",
        ),
        vulnerabilities=[
            Vulnerability(
                file_path="src/api.py",
                line=15,
                column=1,
                severity=Severity.HIGH,
                vulnerability_type="sql_injection",
                description="SQL注入漏洞：用户输入未经过滤直接拼接SQL",
                fix_suggestion={
                    FixStrategy.SAFE: "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
                    FixStrategy.COMPAT: "cursor.execute(f'SELECT * FROM users WHERE id = {int(user_id)}')",
                },
                poc="requests.get('/api/user?id=1 OR 1=1')",
            ),
            Vulnerability(
                file_path="src/api.py",
                line=30,
                column=1,
                severity=Severity.LOW,
                vulnerability_type="logging_sensitive_data",
                description="日志中包含敏感信息",
            ),
        ],
        execution_time=2.5,
        success=True,
    )


class TestMarkdownReporter:
    def test_generates_title(self, sample_result):
        reporter = MarkdownReporter()
        report = reporter.generate(sample_result)
        assert "ClashCode 安全审查报告" in report

    def test_contains_summary(self, sample_result):
        reporter = MarkdownReporter()
        report = reporter.generate(sample_result)
        assert "高风险" in report
        assert "低风险" in report

    def test_contains_mermaid(self, sample_result):
        reporter = MarkdownReporter()
        report = reporter.generate(sample_result)
        assert "```mermaid" in report

    def test_contains_vulnerability_details(self, sample_result):
        reporter = MarkdownReporter()
        report = reporter.generate(sample_result)
        assert "sql_injection" in report
        assert "SQL注入" in report

    def test_contains_fix_suggestions(self, sample_result):
        reporter = MarkdownReporter()
        report = reporter.generate(sample_result)
        assert "安全优先" in report
        assert "兼容优先" in report

    def test_empty_result(self):
        result = AnalysisResult(success=True, execution_time=0.1)
        reporter = MarkdownReporter()
        report = reporter.generate(result)
        assert "未发现安全漏洞" in report

    def test_save_to_file(self, sample_result, tmp_path: Path):
        reporter = MarkdownReporter()
        output = tmp_path / "report.md"
        reporter.generate(sample_result, output)
        assert output.exists()
        assert "ClashCode" in output.read_text()


class TestJSONReporter:
    def test_valid_json(self, sample_result):
        reporter = JSONReporter()
        report = reporter.generate(sample_result)
        data = json.loads(report)
        assert data["success"] is True
        assert len(data["vulnerabilities"]) == 2

    def test_save_to_file(self, sample_result, tmp_path: Path):
        reporter = JSONReporter()
        output = tmp_path / "report.json"
        reporter.generate(sample_result, output)
        data = json.loads(output.read_text())
        assert data["summary"]["high"] == 1


class TestReporterFactory:
    def test_get_markdown(self):
        reporter = ReporterFactory.get_reporter("markdown")
        assert isinstance(reporter, MarkdownReporter)

    def test_get_json(self):
        reporter = ReporterFactory.get_reporter("json")
        assert isinstance(reporter, JSONReporter)

    def test_unknown_format_defaults_markdown(self):
        reporter = ReporterFactory.get_reporter("xml")
        assert isinstance(reporter, MarkdownReporter)
