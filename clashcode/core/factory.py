"""语言适配器工厂，根据文件后缀检测语言并返回对应分析适配器"""

from __future__ import annotations

import logging
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Type

from .models import DependencyGraph, FileChange, ImpactLevel, ImpactNode

logger = logging.getLogger(__name__)

LANGUAGE_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
}


class LanguageAdapter(ABC):
    @abstractmethod
    def extract_changed_functions(self, file_change: FileChange) -> List[str]:
        ...

    @abstractmethod
    def build_dependency_graph(
        self, file_changes: List[FileChange], project_root: str, max_depth: int
    ) -> DependencyGraph:
        ...


class PythonAdapter(LanguageAdapter):
    def extract_changed_functions(self, file_change: FileChange) -> List[str]:
        if not file_change.new_content:
            return []
        functions: List[str] = []
        pattern = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(|^class\s+(\w+)\s*[:\(]", re.MULTILINE)
        for match in pattern.finditer(file_change.new_content):
            name = match.group(1) or match.group(2)
            if name:
                functions.append(name)
        return functions

    def build_dependency_graph(
        self, file_changes: List[FileChange], project_root: str, max_depth: int
    ) -> DependencyGraph:
        graph = DependencyGraph()
        graph.changed_files = [fc.file_path for fc in file_changes]
        changed_functions: List[str] = []
        for fc in file_changes:
            changed_functions.extend(fc.changed_functions)

        # tree-sitter based import analysis
        impacted = self._find_importers(graph.changed_files, project_root, max_depth)
        graph.impacted_files = impacted

        # Build function call map via simple grep
        graph.function_call_map = self._build_call_map(changed_functions, project_root)

        # Build impact nodes
        for f in graph.changed_files:
            for fn in changed_functions:
                graph.impact_nodes.append(ImpactNode(f, fn, ImpactLevel.DIRECT))
        for f in impacted:
            graph.impact_nodes.append(ImpactNode(f, "", ImpactLevel.INDIRECT))

        # Build dependency chains as text
        for cf in graph.changed_files:
            for imp in impacted:
                graph.dependency_chains.append(f"{Path(cf).name} -> {Path(imp).name}")

        return graph

    def _find_importers(self, changed_files: List[str], project_root: str, max_depth: int) -> List[str]:
        importers: set[str] = set()
        root = Path(project_root)
        module_names = set()
        for cf in changed_files:
            p = Path(cf)
            module_names.add(p.stem)
            rel = p.relative_to(root) if p.is_relative_to(root) else p
            module_names.add(str(rel.with_suffix("")).replace("/", ".").replace("\\", "."))

        if not module_names:
            return []

        try:
            for py_file in root.rglob("*.py"):
                if str(py_file) in changed_files:
                    continue
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for mod_name in module_names:
                    if f"import {mod_name}" in content or f"from {mod_name}" in content:
                        importers.add(str(py_file))
                        break
        except Exception as e:
            logger.warning(f"Import scanning error: {e}")

        return list(importers)

    def _build_call_map(self, functions: List[str], project_root: str) -> Dict[str, List[str]]:
        call_map: Dict[str, List[str]] = {}
        root = Path(project_root)
        for func_name in functions:
            callers: List[str] = []
            try:
                result = subprocess.run(
                    ["grep", "-rl", f"{func_name}(", str(root), "--include=*.py"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    callers = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            except Exception:
                pass
            call_map[func_name] = callers
        return call_map


class GenericAdapter(LanguageAdapter):
    """Fallback adapter using simple regex patterns"""

    def extract_changed_functions(self, file_change: FileChange) -> List[str]:
        if not file_change.new_content:
            return []
        functions: List[str] = []
        patterns = [
            re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)"),
            re.compile(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\("),
            re.compile(r"(?:public|private|protected)?\s*(?:static\s+)?(\w+)\s*\([^)]*\)\s*\{"),
            re.compile(r"func\s+(\w+)"),
        ]
        for pattern in patterns:
            for match in pattern.finditer(file_change.new_content):
                name = match.group(1)
                if name and name not in functions:
                    functions.append(name)
        return functions

    def build_dependency_graph(
        self, file_changes: List[FileChange], project_root: str, max_depth: int
    ) -> DependencyGraph:
        graph = DependencyGraph()
        graph.changed_files = [fc.file_path for fc in file_changes]
        return graph


class AdapterFactory:
    _adapters: Dict[str, Type[LanguageAdapter]] = {
        "python": PythonAdapter,
        "javascript": GenericAdapter,
        "typescript": GenericAdapter,
        "go": GenericAdapter,
        "java": GenericAdapter,
    }

    @classmethod
    def detect_language(cls, file_path: str) -> Optional[str]:
        suffix = Path(file_path).suffix.lower()
        return LANGUAGE_MAP.get(suffix)

    @classmethod
    def get_adapter(cls, language: str) -> LanguageAdapter:
        adapter_cls = cls._adapters.get(language, GenericAdapter)
        return adapter_cls()
