"""分析报告生成器 - Markdown / JSON 格式报告"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .models import AnalysisResult, Severity

logger = logging.getLogger(__name__)


class MarkdownReporter:
    def generate(self, result: AnalysisResult, output_path: Optional[Path] = None) -> str:
        lines: list[str] = []

        lines.append("# ClashCode 安全审查报告\n")

        # Summary
        lines.append("## 概览\n")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 分析耗时 | {result.execution_time:.2f}s |")
        lines.append(f"| 变更文件数 | {len(result.file_changes)} |")
        lines.append(f"| 发现漏洞总数 | {len(result.vulnerabilities)} |")
        lines.append(f"| 🔴 高风险 | {result.high_risk_count} |")
        lines.append(f"| 🟡 中风险 | {result.medium_risk_count} |")
        lines.append(f"| 🟢 低风险 | {result.low_risk_count} |")
        lines.append("")

        if not result.success:
            lines.append(f"> ⚠️ 分析过程出错: {result.error_message}\n")

        # Dependency graph
        if result.dependency_graph and result.dependency_graph.mermaid_code:
            lines.append("## 全局依赖影响链\n")
            lines.append("```mermaid")
            lines.append(result.dependency_graph.mermaid_code)
            lines.append("```\n")

            if result.dependency_graph.impacted_files:
                lines.append("### 受影响文件列表\n")
                for f in result.dependency_graph.impacted_files:
                    lines.append(f"- `{f}`")
                lines.append("")

        # Vulnerabilities
        if result.vulnerabilities:
            lines.append("## 漏洞详情\n")

            severity_groups = {
                Severity.HIGH: [],
                Severity.MEDIUM: [],
                Severity.LOW: [],
            }
            for v in result.vulnerabilities:
                severity_groups[v.severity].append(v)

            severity_icons = {
                Severity.HIGH: "🔴 高风险",
                Severity.MEDIUM: "🟡 中风险",
                Severity.LOW: "🟢 低风险",
            }

            for severity in [Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
                vulns = severity_groups[severity]
                if not vulns:
                    continue

                lines.append(f"### {severity_icons[severity]} ({len(vulns)})\n")

                for i, v in enumerate(vulns, 1):
                    lines.append(f"#### {i}. {v.vulnerability_type}\n")
                    lines.append(f"- **位置**: `{v.file_path}:{v.line}:{v.column}`")
                    lines.append(f"- **描述**: {v.description}")

                    if v.poc:
                        lines.append("- **POC**:")
                        lines.append(f"```python\n{v.poc}\n```")

                    if v.fix_suggestion:
                        lines.append("\n**修复方案**:\n")
                        strategy_names = {
                            "safe": "🛡️ 安全优先",
                            "compat": "🔄 兼容优先",
                            "performance": "⚡ 性能优先",
                        }
                        for strategy, code in v.fix_suggestion.items():
                            name = strategy_names.get(strategy.value, strategy.value)
                            if code:
                                lines.append(f"<details><summary>{name}</summary>\n")
                                lines.append(f"```python\n{code}\n```\n")
                                lines.append("</details>\n")

                    lines.append("---\n")
        else:
            lines.append("## ✅ 未发现安全漏洞\n")
            lines.append("代码审查通过，未检测到安全风险。\n")

        # Changed files
        if result.file_changes:
            lines.append("## 变更文件\n")
            for fc in result.file_changes:
                lines.append(
                    f"- `{fc.file_path}` ({fc.change_type.value})"
                    + (f" - 变更函数: {', '.join(fc.changed_functions)}" if fc.changed_functions else "")
                )
            lines.append("")

        report = "\n".join(lines)

        if output_path:
            output_path.write_text(report, encoding="utf-8")
            logger.info(f"Report saved to {output_path}")

        return report


class JSONReporter:
    def generate(self, result: AnalysisResult, output_path: Optional[Path] = None) -> str:
        data = result.to_json()
        report = json.dumps(data, ensure_ascii=False, indent=2)
        if output_path:
            output_path.write_text(report, encoding="utf-8")
        return report


class ReporterFactory:
    _reporters = {
        "markdown": MarkdownReporter,
        "json": JSONReporter,
    }

    @classmethod
    def get_reporter(cls, fmt: str) -> MarkdownReporter | JSONReporter:
        reporter_cls = cls._reporters.get(fmt, MarkdownReporter)
        return reporter_cls()
