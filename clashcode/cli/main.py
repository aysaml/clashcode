"""ClashCode CLI - 基于 Typer 的命令行入口"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel

from ..core.config import Config
from ..core.orchestrator import ClashCodeOrchestrator

app = typer.Typer(
    name="clashcode",
    help="ClashCode - AI编码原生安全助手，红蓝对抗代码审查 + 全局影响分析",
    no_args_is_help=True,
)
console = Console()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def _get_orchestrator(
    project_root: Optional[Path] = None,
) -> ClashCodeOrchestrator:
    root = project_root or Path.cwd()
    config = Config.load(root)
    return ClashCodeOrchestrator(config, root)


@app.command()
def analyze(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="指定要审查的文件路径"),
    git_ref: Optional[str] = typer.Option(None, "--git-ref", "-g", help="Git 提交引用 (如 HEAD~1)"),
    code: Optional[str] = typer.Option(None, "--code", "-c", help="直接传入代码片段"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="报告输出路径"),
    report_format: str = typer.Option("markdown", "--format", help="报告格式: markdown / json"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON 格式结果"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志输出"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="项目根目录"),
) -> None:
    """审查代码安全风险，执行红蓝对抗分析"""
    setup_logging(verbose)

    with console.status("[bold cyan]正在分析代码...[/]"):
        orchestrator = _get_orchestrator(Path(project) if project else None)
        result = orchestrator.analyze(
            git_ref=git_ref,
            target_file=file,
            selected_code=code,
            report_format="json" if json_output else report_format,
            output_path=Path(output) if output else None,
        )

    if json_output:
        console.print_json(json.dumps(result.to_json(), ensure_ascii=False))
    else:
        console.print(Markdown(result.markdown_report))
        if result.vulnerabilities:
            high = result.high_risk_count
            med = result.medium_risk_count
            low = result.low_risk_count
            console.print(
                Panel(
                    f"[red]高风险: {high}[/] | [yellow]中风险: {med}[/] | [green]低风险: {low}[/]",
                    title="审查结果摘要",
                    border_style="bold",
                )
            )
        else:
            console.print(Panel("✅ 未发现安全漏洞", style="green"))

    if not result.success:
        raise typer.Exit(code=1)


@app.command()
def impact(
    file: Optional[str] = typer.Option(None, "--file", "-f", help="分析指定文件的影响范围"),
    git_ref: Optional[str] = typer.Option(None, "--git-ref", "-g", help="Git 提交引用"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
) -> None:
    """分析代码变更的全局影响范围"""
    setup_logging(verbose)

    with console.status("[bold cyan]正在分析依赖影响...[/]"):
        orchestrator = _get_orchestrator(Path(project) if project else None)
        from ..core.git_detector import GitChangeDetector
        from ..core.impact_analyzer import ImpactAnalyzer

        detector = GitChangeDetector(orchestrator.project_root)
        if file:
            changes = detector.get_file_changes(file)
        elif git_ref:
            changes = detector.get_committed_changes(git_ref)
        else:
            changes = detector.get_staged_changes()

        if not changes:
            console.print("[yellow]未检测到代码变更[/]")
            return

        analyzer = ImpactAnalyzer(orchestrator.project_root, orchestrator.config.analysis)
        graph = analyzer.build_dependency_graph(changes)

    console.print(Markdown(f"## 全局影响分析\n\n{analyzer.get_impact_summary(graph)}"))
    if graph.mermaid_code:
        console.print(Panel(graph.mermaid_code, title="依赖图谱 (Mermaid)", border_style="cyan"))


@app.command()
def fix(
    vuln_id: str = typer.Argument(..., help="漏洞 ID"),
    strategy: str = typer.Option("safe", "--strategy", "-s", help="修复策略: safe/compat/performance"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """修复指定漏洞"""
    setup_logging(verbose)
    console.print("[yellow]修复功能需要配合分析结果使用，请通过 MCP 或 CLI analyze 先获取漏洞信息[/]")
    console.print(f"漏洞 ID: {vuln_id}, 策略: {strategy}")


@app.command()
def rollback(
    file: str = typer.Argument(..., help="要回滚的文件路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
) -> None:
    """回滚文件到最近一次备份"""
    setup_logging(verbose)

    orchestrator = _get_orchestrator(Path(project) if project else None)
    success = orchestrator.rollback(file)
    if success:
        console.print(f"[green]✅ 已回滚 {file}[/]")
    else:
        console.print(f"[red]❌ 回滚失败: 未找到 {file} 的备份[/]")
        raise typer.Exit(code=1)


@app.command()
def init(
    project: Optional[str] = typer.Option(None, "--project", "-p"),
) -> None:
    """初始化项目配置文件 (.clashcode.yml)"""
    root = Path(project) if project else Path.cwd()
    config_path = root / ".clashcode.yml"
    if config_path.exists():
        console.print(f"[yellow]配置文件已存在: {config_path}[/]")
        return

    config = Config()
    config.save(config_path)
    console.print(f"[green]✅ 配置文件已创建: {config_path}[/]")
    console.print("请编辑配置文件设置 LLM API Key 等参数。")


@app.command()
def version() -> None:
    """显示版本信息"""
    from .. import __version__

    console.print(f"ClashCode v{__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
