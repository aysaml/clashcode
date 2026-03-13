"""全流程编排器 - 串联所有模块，对外暴露统一 API"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional

from .backup import BackupManager
from .config import Config
from .git_detector import GitChangeDetector
from .impact_analyzer import ImpactAnalyzer
from .llm import LLMClientFactory
from .models import AnalysisResult, FixStrategy, Vulnerability
from .red_blue_team import RedBlueTeamEngine
from .reporters import ReporterFactory

logger = logging.getLogger(__name__)


class ClashCodeOrchestrator:
    def __init__(self, config: Config, project_root: Optional[Path] = None):
        self.config = config
        self.project_root = project_root or Path.cwd()
        self.backup_manager = BackupManager(self.project_root, config.backup)
        self._impact_analyzer = ImpactAnalyzer(self.project_root, config.analysis)
        self._llm_client = None

    @property
    def llm_client(self):
        if self._llm_client is None:
            self._llm_client = LLMClientFactory.get_client(self.config.llm)
        return self._llm_client

    def analyze(
        self,
        git_ref: Optional[str] = None,
        target_file: Optional[str] = None,
        selected_code: Optional[str] = None,
        report_format: str = "markdown",
        output_path: Optional[Path] = None,
    ) -> AnalysisResult:
        start_time = time.time()
        success = False
        error_message: Optional[str] = None
        file_changes = []
        dependency_graph = None
        vulnerabilities: List[Vulnerability] = []

        try:
            # Step 1: Detect changes
            logger.info("Step 1: Detecting code changes")
            detector = GitChangeDetector(self.project_root)
            if target_file:
                file_changes = detector.get_file_changes(target_file, selected_code)
            elif git_ref:
                file_changes = detector.get_committed_changes(git_ref)
            else:
                file_changes = detector.get_staged_changes()

            if not file_changes:
                logger.warning("No code changes detected")
                return AnalysisResult(
                    file_changes=[],
                    dependency_graph=None,
                    vulnerabilities=[],
                    execution_time=time.time() - start_time,
                    success=True,
                    markdown_report="未检测到代码变更。",
                )

            # Step 2: Build dependency graph
            logger.info("Step 2: Building dependency graph")
            dependency_graph = self._impact_analyzer.build_dependency_graph(file_changes)

            # Step 3: Red-blue team review
            logger.info("Step 3: Running red-blue team review")
            model_selector = self._build_model_selector()
            engine = RedBlueTeamEngine(
                self.llm_client,
                self.config.analysis,
                model_selector=model_selector,
            )
            vulnerabilities = engine.run(file_changes, dependency_graph)

            success = True
            logger.info(f"Analysis complete: found {len(vulnerabilities)} vulnerabilities")

        except Exception as e:
            error_message = str(e)
            logger.error(f"Analysis failed: {error_message}", exc_info=True)

        # Step 4: Generate report
        result = AnalysisResult(
            file_changes=file_changes,
            dependency_graph=dependency_graph,
            vulnerabilities=vulnerabilities,
            execution_time=time.time() - start_time,
            success=success,
            error_message=error_message,
        )

        logger.info("Step 4: Generating report")
        reporter = ReporterFactory.get_reporter(report_format)
        result.markdown_report = reporter.generate(result, output_path)

        return result

    def _build_model_selector(self):
        """根据配置构建模型选择器，strategy=fixed 时返回 None（向后兼容）"""
        from .model_selector import ModelSelectionConfig, ModelSelectionStrategy, ModelSelector

        strategy_str = self.config.analysis.model_selection_strategy
        if strategy_str == "fixed":
            return None

        try:
            strategy = ModelSelectionStrategy(strategy_str)
        except ValueError:
            logger.warning(f"Unknown model selection strategy: {strategy_str}, falling back to fixed")
            return None

        selection_config = ModelSelectionConfig(
            strategy=strategy,
            assigned_models=dict(self.config.analysis.assigned_models),
            prefer_different_vendors=self.config.analysis.prefer_different_vendors,
            excluded_models=list(self.config.analysis.excluded_models),
            candidate_models=list(self.config.analysis.candidate_models),
        )

        return ModelSelector(
            user_llm_config=self.config.llm,
            selection_config=selection_config,
        )

    def fix(
        self,
        vulnerability: Vulnerability,
        strategy: FixStrategy = FixStrategy.SAFE,
    ) -> bool:
        try:
            file_path = Path(vulnerability.file_path)
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                return False

            self.backup_manager.backup(file_path)

            fix_code = vulnerability.fix_suggestion.get(strategy, "")
            if not fix_code:
                logger.error(f"No fix suggestion for strategy: {strategy}")
                return False

            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            line_idx = vulnerability.line - 1
            if 0 <= line_idx < len(lines):
                lines[line_idx] = fix_code
            else:
                logger.error(f"Invalid line number: {vulnerability.line}")
                return False

            new_content = "\n".join(lines)
            file_path.write_text(new_content, encoding="utf-8")
            logger.info(f"Fixed {file_path}:{vulnerability.line}")
            return True

        except Exception as e:
            logger.error(f"Fix failed: {e}")
            return False

    def batch_fix(
        self,
        vulnerabilities: List[Vulnerability],
        strategy: FixStrategy = FixStrategy.SAFE,
        skip_high_risk: bool = True,
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}
        from .models import Severity

        for vuln in vulnerabilities:
            if skip_high_risk and vuln.severity == Severity.HIGH:
                results[vuln.id] = False
                logger.warning(f"Skipped high-risk vuln (requires manual confirmation): {vuln.id}")
                continue
            results[vuln.id] = self.fix(vuln, strategy)
        return results

    def rollback(self, file_path: str) -> bool:
        return self.backup_manager.rollback(Path(file_path))

    def verify(self, file_path: str) -> AnalysisResult:
        return self.analyze(target_file=file_path)

    def get_rollback_diff(self, file_path: str) -> Optional[tuple[str, str]]:
        return self.backup_manager.get_backup_diff(Path(file_path))
