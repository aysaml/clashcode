"""全局影响分析模块 - 基于依赖图谱构建、Mermaid 可视化、分级展示"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from .config import AnalysisConfig
from .factory import AdapterFactory
from .models import DependencyGraph, FileChange, ImpactLevel

logger = logging.getLogger(__name__)


class ImpactAnalyzer:
    def __init__(self, project_root: Path, config: AnalysisConfig):
        self.project_root = project_root
        self.config = config
        self._cache: dict[str, DependencyGraph] = {}

    def build_dependency_graph(self, file_changes: List[FileChange]) -> DependencyGraph:
        cache_key = "|".join(sorted(fc.file_path for fc in file_changes))
        if cache_key in self._cache:
            logger.info("Using cached dependency graph")
            return self._cache[cache_key]

        lang = self._detect_language(file_changes)
        if not lang:
            logger.warning("Cannot detect project language, using minimal graph")
            graph = DependencyGraph(
                changed_files=[fc.file_path for fc in file_changes]
            )
            graph.mermaid_code = self._generate_mermaid(graph)
            return graph

        adapter = AdapterFactory.get_adapter(lang)
        graph = adapter.build_dependency_graph(
            file_changes, str(self.project_root), self.config.max_dependency_depth
        )
        graph.mermaid_code = self._generate_mermaid(graph)

        self._cache[cache_key] = graph
        logger.info(f"Dependency graph built: {len(graph.impacted_files)} impacted files")
        return graph

    def _detect_language(self, file_changes: List[FileChange]) -> Optional[str]:
        if self.config.target_language:
            return self.config.target_language
        for fc in file_changes:
            detected = AdapterFactory.detect_language(fc.file_path)
            if detected:
                return detected
        return None

    def _generate_mermaid(self, graph: DependencyGraph) -> str:
        lines = ["flowchart LR"]

        # Style definitions
        lines.append("    classDef changed fill:#ff6b6b,stroke:#c92a2a,color:#fff")
        lines.append("    classDef direct fill:#ffa94d,stroke:#e8590c,color:#fff")
        lines.append("    classDef indirect fill:#74c0fc,stroke:#1971c2,color:#fff")
        lines.append("    classDef edge fill:#b2f2bb,stroke:#2f9e44,color:#333")

        # Changed nodes
        for i, f in enumerate(graph.changed_files):
            name = Path(f).name
            lines.append(f'    C{i}["{name}<br/>(变更文件)"]:::changed')

        # Impact nodes grouped by level
        direct_files = []
        indirect_files = []
        edge_files = []
        for node in graph.impact_nodes:
            if node.impact_level == ImpactLevel.DIRECT and node.file_path not in graph.changed_files:
                direct_files.append(node.file_path)
            elif node.impact_level == ImpactLevel.INDIRECT:
                indirect_files.append(node.file_path)
            elif node.impact_level == ImpactLevel.EDGE:
                edge_files.append(node.file_path)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_impacted = []
        for f in graph.impacted_files:
            if f not in seen and f not in graph.changed_files:
                seen.add(f)
                unique_impacted.append(f)

        for i, f in enumerate(unique_impacted):
            name = Path(f).name
            if f in direct_files:
                lines.append(f'    D{i}["{name}"]:::direct')
            elif f in indirect_files:
                lines.append(f'    D{i}["{name}"]:::indirect')
            else:
                lines.append(f'    D{i}["{name}"]:::edge')

        # Edges
        for ci, cf in enumerate(graph.changed_files):
            for di, df in enumerate(unique_impacted):
                for chain in graph.dependency_chains:
                    cf_name = Path(cf).name
                    df_name = Path(df).name
                    if cf_name in chain and df_name in chain:
                        lines.append(f"    C{ci} --> D{di}")
                        break

        # Function call edges
        for func, callers in graph.function_call_map.items():
            func_node = func.replace(".", "_").replace("-", "_")
            for caller in callers[:5]:
                caller_name = Path(caller).name
                caller_node = caller_name.replace(".", "_").replace("-", "_")
                lines.append(f'    {func_node}["{func}()"] -.-> {caller_node}["{caller_name}"]')

        return "\n".join(lines)

    def get_impact_summary(self, graph: DependencyGraph) -> str:
        direct = [n for n in graph.impact_nodes if n.impact_level == ImpactLevel.DIRECT]
        indirect = [n for n in graph.impact_nodes if n.impact_level == ImpactLevel.INDIRECT]
        edge = [n for n in graph.impact_nodes if n.impact_level == ImpactLevel.EDGE]

        lines = [
            "**影响范围概览**",
            f"- 变更文件: {len(graph.changed_files)}",
            f"- 直接影响: {len(direct)} 个节点",
            f"- 间接影响: {len(indirect)} 个节点",
            f"- 边缘影响: {len(edge)} 个节点",
            f"- 受影响文件总数: {len(graph.impacted_files)}",
        ]
        return "\n".join(lines)

    def clear_cache(self) -> None:
        self._cache.clear()
