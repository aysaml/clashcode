"""
ClashCode MCP Server

通过 MCP (Model Context Protocol) 集成到 Cursor/Windsurf/Trae 等 AI 编辑器。
AI 会自动发现并调用这些工具完成代码审查、影响分析、修复、验证等操作。

启动方式: python -m clashcode.mcp.server
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clashcode-mcp")

mcp = FastMCP(
    "ClashCode",
    instructions=(
        "你是 ClashCode 安全助手，专门帮助开发者进行 AI 代码安全审查和全局影响分析。"
        "用户可以要求你审查代码、分析变更影响、修复漏洞、验证修复结果或回滚修改。"
        "请使用提供的工具来完成这些任务，并以清晰的中文向用户报告结果。"
    ),
)


def _get_project_root() -> str:
    cwd = os.getcwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return cwd


def _run_cli(
    *args: str,
    project_root: Optional[str] = None,
    json_output: bool = False,
) -> dict:
    root = project_root or _get_project_root()
    cmd = [sys.executable, "-m", "clashcode.cli.main", *args, "--project", root]
    if json_output:
        cmd.append("--json")
    logger.info(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout = result.stdout.strip()
        if result.returncode == 0:
            if json_output and stdout:
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError:
                    pass
            return {"success": True, "output": stdout}
        else:
            return {
                "success": False,
                "error": result.stderr.strip() or stdout or "Command failed",
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Analysis timed out (120s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _format_report(data: dict) -> str:
    if "markdown_report" in data and data["markdown_report"]:
        return data["markdown_report"]

    if "error" in data and not data.get("success", True):
        return f"**错误**: {data['error']}"

    if "output" in data:
        return data["output"]

    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def check_code(
    file: Optional[str] = None,
    code: Optional[str] = None,
    git_ref: Optional[str] = None,
    focus: Optional[str] = None,
) -> str:
    """审查代码安全风险，执行红蓝对抗分析。

    可以审查：指定文件、选中的代码片段、Git 暂存区变更、指定提交的变更。
    会自动进行红队攻击（漏洞挖掘）→ 仲裁验证（过滤误报）→ 蓝队修复（生成方案）。

    Args:
        file: 要审查的文件路径（相对于项目根目录），如 "src/api.py"
        code: 要审查的代码片段（直接传入代码文本）
        git_ref: Git 提交引用，如 "HEAD~1"，用于审查指定提交的变更
        focus: 聚焦审查场景，如 "权限校验"、"SQL注入"、"支付逻辑"
    """
    args = ["analyze"]
    if file:
        args.extend(["--file", file])
    if code:
        args.extend(["--code", code])
    if git_ref:
        args.extend(["--git-ref", git_ref])

    data = _run_cli(*args, json_output=True)
    return _format_report(data)


@mcp.tool()
def analyze_impact(
    file: Optional[str] = None,
    git_ref: Optional[str] = None,
) -> str:
    """分析代码变更的全局影响范围，展示依赖链和受影响的文件。

    基于 Git 变更识别 + 依赖图谱构建，分析修改会影响哪些文件、接口、模块。
    结果包含 Mermaid 依赖图和分级影响列表（直接/间接/边缘影响）。

    Args:
        file: 要分析影响范围的文件路径
        git_ref: Git 提交引用，如 "HEAD~1"
    """
    args = ["impact"]
    if file:
        args.extend(["--file", file])
    if git_ref:
        args.extend(["--git-ref", git_ref])

    data = _run_cli(*args)
    return _format_report(data)


@mcp.tool()
def rollback_file(file: str) -> str:
    """回滚文件到最近一次修复前的状态。

    ClashCode 在每次修复前会自动备份原文件到 .clashcode_backups/ 目录。
    此工具将指定文件恢复到备份版本。

    Args:
        file: 要回滚的文件路径
    """
    args = ["rollback", file]
    data = _run_cli(*args)

    if data.get("success", False):
        return f"已成功回滚 `{file}` 到修复前状态。"
    return f"回滚失败: {data.get('error', '未找到备份')}"


@mcp.tool()
def init_config() -> str:
    """初始化 ClashCode 项目配置文件 (.clashcode.yml)。

    在当前项目根目录创建默认配置文件，包含 LLM、审查策略、备份等配置项。
    """
    root = _get_project_root()
    config_path = Path(root) / ".clashcode.yml"
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
        return f"配置文件已存在 (`{config_path}`):\n\n```yaml\n{content}\n```"

    data = _run_cli("init")
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
        return f"配置文件已创建 (`{config_path}`):\n\n```yaml\n{content}\n```\n\n请编辑配置文件设置 LLM API Key。"
    return data.get("error", "初始化失败")


@mcp.tool()
def list_backups() -> str:
    """列出当前项目的所有代码备份文件。"""
    root = _get_project_root()
    backup_dir = Path(root) / ".clashcode_backups"
    if not backup_dir.exists():
        return "当前项目没有备份文件。"

    files = sorted(backup_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return "备份目录为空。"

    lines = [f"**备份文件列表** (`{backup_dir}`):\n"]
    for f in files[:20]:
        size = f.stat().st_size
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"- `{f.name}` ({size} bytes, {mtime})")

    return "\n".join(lines)


def main():
    logger.info("Starting ClashCode MCP Server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
