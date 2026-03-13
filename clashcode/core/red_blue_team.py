"""红蓝对抗安全审查引擎 - 三智能体自动化漏洞挖掘与修复，支持每个智能体独立选用不同模型"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from .config import AnalysisConfig
from .llm import BaseLLMClient
from .models import (
    ChangeType,
    DependencyGraph,
    FileChange,
    FixStrategy,
    Severity,
    Vulnerability,
)

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    file_change: Dict[str, Any]
    dependency_context: str
    is_high_priority: bool
    focus_scenarios: List[str]
    attack_results: List[Dict[str, Any]]
    validated_results: List[Dict[str, Any]]
    fix_suggestions: Dict[str, Dict[str, str]]
    vulnerabilities: List[Dict[str, Any]]


class RedBlueTeamEngine:
    """红蓝对抗引擎

    支持两种模型使用方式:
    1. 单一模型: 传入 llm_client，三个智能体共用（向后兼容）
    2. 独立模型: 通过 model_selector 为每个智能体分配不同模型
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        config: AnalysisConfig,
        model_selector: Optional[Any] = None,
    ):
        self.llm_client = llm_client
        self.config = config
        self._model_selector = model_selector
        self._init_agent_clients()

    def _init_agent_clients(self) -> None:
        """初始化每个智能体的 LLM Client，支持独立模型分配"""
        if self._model_selector is not None:
            from .model_selector import AgentRole, ModelSelector

            selector: ModelSelector = self._model_selector
            selector.select_models()
            self._red_client = selector.get_client_for_role(AgentRole.RED_TEAM)
            self._arbitrator_client = selector.get_client_for_role(AgentRole.ARBITRATOR)
            self._blue_client = selector.get_client_for_role(AgentRole.BLUE_TEAM)
            logger.info(f"Agent model assignment:\n{selector.get_assignment_summary()}")
        else:
            self._red_client = self.llm_client
            self._arbitrator_client = self.llm_client
            self._blue_client = self.llm_client

    def run(
        self,
        file_changes: List[FileChange],
        dependency_graph: DependencyGraph,
    ) -> List[Vulnerability]:
        vulnerabilities: List[Vulnerability] = []

        high_priority_files = [
            fc for fc in file_changes if fc.change_type != ChangeType.DELETED
        ]
        medium_priority_files = [
            fc
            for fc in file_changes
            if fc.file_path in dependency_graph.impacted_files
            and fc not in high_priority_files
        ]

        for fc in high_priority_files:
            vulns = self._review_file(fc, dependency_graph, is_high_priority=True)
            vulnerabilities.extend(vulns)

        for fc in medium_priority_files:
            vulns = self._review_file(fc, dependency_graph, is_high_priority=False)
            vulnerabilities.extend(vulns)

        severity_order = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}
        threshold = severity_order[self.config.severity_threshold]
        return [v for v in vulnerabilities if severity_order[v.severity] >= threshold]

    def _review_file(
        self,
        file_change: FileChange,
        dependency_graph: DependencyGraph,
        is_high_priority: bool,
    ) -> List[Vulnerability]:
        vulnerabilities: List[Vulnerability] = []
        rounds = self.config.adversarial_rounds if is_high_priority else 1

        for round_num in range(rounds):
            logger.info(
                f"Reviewing {file_change.file_path} - round {round_num + 1}/{rounds}"
            )

            try:
                # Step 1: Red team attack
                attack_results = self._red_team_attack(
                    file_change, dependency_graph, is_high_priority
                )
                if not attack_results:
                    continue

                # Step 2: Arbitrator validation
                validated = self._arbitrator_validate(attack_results, file_change)
                if not validated:
                    continue

                # Step 3: Blue team fix
                for vuln_data in validated:
                    fix_suggestions = self._blue_team_fix(vuln_data, file_change)
                    vulnerability = self._build_vulnerability(
                        file_change, vuln_data, fix_suggestions
                    )
                    vulnerabilities.append(vulnerability)

            except Exception as e:
                logger.error(f"Review round failed: {e}")
                continue

        return vulnerabilities

    def _red_team_attack(
        self,
        file_change: FileChange,
        dependency_graph: DependencyGraph,
        is_high_priority: bool,
    ) -> List[Dict[str, Any]]:
        dep_context = "\n".join(dependency_graph.dependency_chains[:10])
        scenario_hint = ""
        if self.config.focus_scenarios:
            scenario_hint = f"\n重点审查场景: {', '.join(self.config.focus_scenarios)}"

        depth_hint = "深度对抗审查" if is_high_priority else "基础安全扫描"

        prompt = f"""你是专业的红队安全专家，专门挖掘AI生成代码的隐性逻辑漏洞。
本次审查级别: {depth_hint}

【审查上下文】
文件路径: {file_change.file_path}
变更的函数: {', '.join(file_change.changed_functions)}
依赖影响链:
{dep_context}
{scenario_hint}

代码内容:
```
{file_change.new_content[:3000] if file_change.new_content else '(empty)'}
```

【审查要求】
1. 重点挖掘: 业务逻辑漏洞、权限绕过、边界条件缺失、并发安全、SQL注入、XSS、SSRF、路径遍历等AI高频错误
2. 分析代码的上下文语义，而非仅做模式匹配
3. 禁止误报，只输出真实可利用的漏洞

请输出JSON数组格式，每个元素包含:
- line: 行号(int)
- column: 列号(int)
- severity: "high"/"medium"/"low"
- vulnerability_type: 漏洞类型
- description: 漏洞描述(中文)
- poc: 验证脚本(可选)

如果没有发现漏洞，返回空数组 []"""

        try:
            result = self._red_client.chat_with_structured_output(
                [{"role": "user", "content": prompt}]
            )
            if isinstance(result, dict):
                if "items" in result:
                    return result["items"]
                if "line" in result:
                    return [result]
            return []
        except Exception as e:
            logger.error(f"Red team attack failed: {e}")
            return []

    def _arbitrator_validate(
        self,
        attack_results: List[Dict[str, Any]],
        file_change: FileChange,
    ) -> List[Dict[str, Any]]:
        if not attack_results:
            return []

        import json

        prompt = f"""你是中立的安全仲裁专家，验证红队发现的漏洞是否真实有效。

红队发现的漏洞:
{json.dumps(attack_results, ensure_ascii=False, indent=2)}

被审查的代码:
```
{file_change.new_content[:3000] if file_change.new_content else '(empty)'}
```

请逐个验证每个漏洞，判断:
1. 该漏洞是否在代码中真实存在
2. 是否能被实际利用
3. 是否为误报

输出JSON数组，仅包含验证通过的漏洞，保留原始字段并添加:
- validation_reason: 验证通过的理由

如果全部为误报，返回空数组 []"""

        try:
            result = self._arbitrator_client.chat_with_structured_output(
                [{"role": "user", "content": prompt}]
            )
            if isinstance(result, dict):
                if "items" in result:
                    return result["items"]
                if "line" in result:
                    return [result]
            return []
        except Exception as e:
            logger.error(f"Arbitrator validation failed: {e}")
            return attack_results  # Fail-open: pass to blue team

    def _blue_team_fix(
        self,
        vuln_data: Dict[str, Any],
        file_change: FileChange,
    ) -> Dict[FixStrategy, str]:
        import json

        prompt = f"""你是专业的蓝队安全专家，针对以下漏洞生成3套差异化修复方案。

漏洞信息:
{json.dumps(vuln_data, ensure_ascii=False, indent=2)}

原代码:
```
{file_change.new_content[:3000] if file_change.new_content else '(empty)'}
```

输出3套修复方案的JSON:
{{
  "safe": "安全优先修复方案 - 完整修复后的代码片段",
  "compat": "兼容优先修复方案 - 最小改动的代码片段",
  "performance": "性能优先修复方案 - 兼顾安全与效率的代码片段"
}}

每个方案只输出需要替换的代码片段（包含漏洞行的上下文），不要输出全文件代码。"""

        try:
            result = self._blue_client.chat_with_structured_output(
                [{"role": "user", "content": prompt}]
            )
            return {
                FixStrategy.SAFE: result.get("safe", ""),
                FixStrategy.COMPAT: result.get("compat", ""),
                FixStrategy.PERFORMANCE: result.get("performance", ""),
            }
        except Exception as e:
            logger.error(f"Blue team fix generation failed: {e}")
            return {}

    def _build_vulnerability(
        self,
        file_change: FileChange,
        vuln_data: Dict[str, Any],
        fix_suggestions: Dict[FixStrategy, str],
    ) -> Vulnerability:
        severity_str = vuln_data.get("severity", "medium").lower()
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.MEDIUM

        return Vulnerability(
            file_path=file_change.file_path,
            line=int(vuln_data.get("line", 1)),
            column=int(vuln_data.get("column", 1)),
            severity=severity,
            vulnerability_type=vuln_data.get("vulnerability_type", "unknown"),
            description=vuln_data.get("description", ""),
            fix_suggestion=fix_suggestions,
            poc=vuln_data.get("poc"),
        )
