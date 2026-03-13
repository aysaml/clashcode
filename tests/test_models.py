"""models.py 单元测试"""

import pytest
from clashcode.core.models import (
    AnalysisResult,
    ChangeType,
    DependencyGraph,
    FileChange,
    FixStrategy,
    Severity,
    Vulnerability,
)


class TestChangeType:
    def test_enum_values(self):
        assert ChangeType.ADDED.value == "A"
        assert ChangeType.MODIFIED.value == "M"
        assert ChangeType.DELETED.value == "D"

    def test_from_value(self):
        assert ChangeType("A") == ChangeType.ADDED
        assert ChangeType("M") == ChangeType.MODIFIED


class TestFileChange:
    def test_defaults(self):
        fc = FileChange(file_path="test.py", change_type=ChangeType.MODIFIED)
        assert fc.old_content is None
        assert fc.new_content is None
        assert fc.changed_functions == []

    def test_with_functions(self):
        fc = FileChange(
            file_path="test.py",
            change_type=ChangeType.ADDED,
            new_content="def foo(): pass",
            changed_functions=["foo"],
        )
        assert fc.changed_functions == ["foo"]


class TestVulnerability:
    def test_auto_id(self):
        v = Vulnerability(
            file_path="test.py",
            line=10,
            column=1,
            severity=Severity.HIGH,
            vulnerability_type="sql_injection",
            description="SQL injection vulnerability",
        )
        assert v.id == "test.py:10:sql_injection"

    def test_custom_id(self):
        v = Vulnerability(
            file_path="test.py",
            line=10,
            column=1,
            severity=Severity.HIGH,
            vulnerability_type="xss",
            description="XSS",
            id="custom-id-123",
        )
        assert v.id == "custom-id-123"


class TestAnalysisResult:
    def test_risk_counts(self):
        result = AnalysisResult(
            vulnerabilities=[
                Vulnerability("a.py", 1, 1, Severity.HIGH, "t", "d"),
                Vulnerability("b.py", 2, 1, Severity.HIGH, "t", "d"),
                Vulnerability("c.py", 3, 1, Severity.MEDIUM, "t", "d"),
                Vulnerability("d.py", 4, 1, Severity.LOW, "t", "d"),
            ],
            success=True,
        )
        assert result.high_risk_count == 2
        assert result.medium_risk_count == 1
        assert result.low_risk_count == 1

    def test_to_json(self):
        result = AnalysisResult(
            file_changes=[
                FileChange("test.py", ChangeType.MODIFIED, changed_functions=["foo"])
            ],
            vulnerabilities=[
                Vulnerability(
                    "test.py", 10, 1, Severity.HIGH, "xss", "XSS found",
                    fix_suggestion={FixStrategy.SAFE: "fixed code"},
                )
            ],
            execution_time=1.234,
            success=True,
        )
        data = result.to_json()
        assert data["success"] is True
        assert data["execution_time"] == 1.234
        assert len(data["vulnerabilities"]) == 1
        assert data["vulnerabilities"][0]["severity"] == "high"
        assert data["summary"]["total"] == 1
        assert data["summary"]["high"] == 1

    def test_empty_result_json(self):
        result = AnalysisResult(success=True)
        data = result.to_json()
        assert data["success"] is True
        assert data["summary"]["total"] == 0
