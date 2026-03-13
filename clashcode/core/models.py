"""全链路统一数据结构定义，模块间数据传递统一格式"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ChangeType(Enum):
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"


class Severity(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FixStrategy(Enum):
    SAFE = "safe"
    COMPAT = "compat"
    PERFORMANCE = "performance"


class ImpactLevel(Enum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    EDGE = "edge"


@dataclass
class FileChange:
    file_path: str
    change_type: ChangeType
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    changed_functions: List[str] = field(default_factory=list)
    start_line: Optional[int] = None
    end_line: Optional[int] = None


@dataclass
class ImpactNode:
    file_path: str
    function_name: str
    impact_level: ImpactLevel
    line: int = 0


@dataclass
class DependencyGraph:
    changed_files: List[str] = field(default_factory=list)
    impacted_files: List[str] = field(default_factory=list)
    dependency_chains: List[str] = field(default_factory=list)
    function_call_map: Dict[str, List[str]] = field(default_factory=dict)
    impact_nodes: List[ImpactNode] = field(default_factory=list)
    mermaid_code: str = ""


@dataclass
class Vulnerability:
    file_path: str
    line: int
    column: int
    severity: Severity
    vulnerability_type: str
    description: str
    fix_suggestion: Dict[FixStrategy, str] = field(default_factory=dict)
    poc: Optional[str] = None
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"{self.file_path}:{self.line}:{self.vulnerability_type}"


@dataclass
class AnalysisResult:
    file_changes: List[FileChange] = field(default_factory=list)
    dependency_graph: Optional[DependencyGraph] = None
    vulnerabilities: List[Vulnerability] = field(default_factory=list)
    execution_time: float = 0.0
    success: bool = False
    error_message: Optional[str] = None
    markdown_report: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def high_risk_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.HIGH)

    @property
    def medium_risk_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.MEDIUM)

    @property
    def low_risk_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == Severity.LOW)

    def to_json(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "execution_time": round(self.execution_time, 3),
            "error_message": self.error_message,
            "file_changes": [
                {
                    "file_path": fc.file_path,
                    "change_type": fc.change_type.value,
                    "changed_functions": fc.changed_functions,
                }
                for fc in self.file_changes
            ],
            "dependency_graph": {
                "changed_files": self.dependency_graph.changed_files,
                "impacted_files": self.dependency_graph.impacted_files,
                "mermaid_code": self.dependency_graph.mermaid_code,
                "function_call_map": self.dependency_graph.function_call_map,
            }
            if self.dependency_graph
            else None,
            "vulnerabilities": [
                {
                    "id": v.id,
                    "file_path": v.file_path,
                    "line": v.line,
                    "column": v.column,
                    "severity": v.severity.value,
                    "vulnerability_type": v.vulnerability_type,
                    "description": v.description,
                    "fix_suggestion": {k.value: val for k, val in v.fix_suggestion.items()},
                    "poc": v.poc,
                }
                for v in self.vulnerabilities
            ],
            "summary": {
                "total": len(self.vulnerabilities),
                "high": self.high_risk_count,
                "medium": self.medium_risk_count,
                "low": self.low_risk_count,
            },
            "markdown_report": self.markdown_report,
        }
