# ClashCode - AI编码原生安全助手

> 你的AI编码原生安全助手，一行代码改完，全链路风险可见

ClashCode 是一款代码安全与全局影响分析工具，以「多智能体红蓝对抗」为核心技术，通过 **MCP (Model Context Protocol)** 原生集成到 Cursor、Windsurf、Trae 等所有支持 MCP 的 AI 编辑器。

## 核心功能

- **红蓝对抗安全审查** - 三智能体（红队攻击 -> 仲裁验证 -> 蓝队修复）自动化漏洞挖掘
- **全局影响分析** - 基于 Git 变更 + 依赖图谱，可视化展示代码变更的全链路影响
- **一键修复验证** - 3 套差异化修复方案 + 增量验证闭环
- **安全兜底** - 自动备份 + 一键回滚 + 零代码上传
- **通用 MCP 集成** - 一套 Server 适配所有 MCP 兼容的 AI 编辑器

## 快速开始

### 1. 安装

```bash
pip install clashcode
```

或从源码安装：

```bash
git clone https://github.com/clashcode/clashcode.git
cd clashcode
pip install poetry
poetry install
```

### 2. 初始化配置

```bash
clashcode init
```

编辑生成的 `.clashcode.yml`：

```yaml
llm:
  provider: openai          # openai / anthropic / ollama / tongyi
  model: gpt-4o
  temperature: 0.1

analysis:
  severity_threshold: low
  adversarial_rounds: 2
  model_selection_strategy: fixed  # fixed / random / assign
  # random 模式需要配置候选模型列表:
  # candidate_models:
  #   - provider: openai
  #     model: gpt-4o
  #   - provider: anthropic
  #     model: claude-3.5-sonnet
  #   - provider: ollama
  #     model: llama3

backup:
  auto_backup: true
  max_backups: 10
```

### 3. 配置 AI 编辑器 MCP

#### Cursor

在项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "clashcode": {
      "command": "python3",
      "args": ["-m", "clashcode.mcp.server"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

重启 Cursor，在 **Settings -> MCP** 确认 `clashcode` 状态为绿色。

#### Windsurf

在 `~/.windsurf/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "clashcode": {
      "command": "python3",
      "args": ["-m", "clashcode.mcp.server"]
    }
  }
}
```

#### 其他 MCP 兼容编辑器

只需配置 MCP Server 的启动命令 `python3 -m clashcode.mcp.server`（stdio 传输），具体格式参考对应编辑器文档。

### 4. 在 AI 聊天中使用

配置完成后，直接在 AI 聊天框中用自然语言：

```
帮我审查 src/api.py 这个文件的安全风险
分析当前暂存区变更的全局影响
回滚 src/api.py 到修复前的状态
初始化 ClashCode 配置
```

AI 会自动调用 ClashCode 的 MCP 工具完成操作。

### 5. CLI 使用

也可以直接用命令行：

```bash
clashcode analyze                        # 审查暂存区变更
clashcode analyze --file src/api.py      # 审查指定文件
clashcode analyze --json                 # JSON 输出
clashcode impact --file src/utils.py     # 全局影响分析
clashcode rollback src/api.py            # 回滚文件
```

## MCP 工具列表

| 工具 | 功能 |
|------|------|
| `check_code` | 红蓝对抗安全审查（文件/代码片段/Git 变更） |
| `analyze_impact` | 全局依赖影响分析 |
| `rollback_file` | 回滚文件到修复前状态 |
| `init_config` | 初始化 .clashcode.yml 配置 |
| `list_backups` | 查看备份文件列表 |

## 项目结构

```
clashcode/
├── clashcode/
│   ├── core/               # 核心引擎
│   │   ├── models.py       # 统一数据结构
│   │   ├── config.py       # 配置管理
│   │   ├── llm.py          # LLM 客户端抽象
│   │   ├── factory.py      # 语言适配器工厂
│   │   ├── git_detector.py # Git 变更识别
│   │   ├── impact_analyzer.py  # 依赖图谱构建
│   │   ├── red_blue_team.py    # 红蓝对抗引擎
│   │   ├── model_selector.py   # 智能体模型分配
│   │   ├── orchestrator.py # 全流程编排器
│   │   ├── backup.py       # 备份与回滚
│   │   └── reporters.py    # 报告生成器
│   ├── cli/                # CLI 入口
│   │   └── main.py
│   └── mcp/                # MCP Server
│       └── server.py
├── tests/                  # 单元测试
├── pyproject.toml
└── .cursor/mcp.json        # Cursor MCP 配置
```

## 支持的 LLM

| 提供商 | provider 值 | 说明 |
|--------|------------|------|
| OpenAI | `openai` | GPT-4o 等 |
| Anthropic | `anthropic` | Claude 系列 |
| 通义千问 | `tongyi` | 阿里云 |
| Ollama | `ollama` | 本地模型，零数据泄露 |

## 开发

```bash
poetry install
poetry run pytest -v --cov=clashcode
```

## 安全说明

- **零代码上传**: 所有代码分析在本地完成，仅向 LLM 传递必要代码片段
- **自动备份**: 修复前自动备份原文件，支持一键回滚
- **无静默修改**: 所有代码修复必须经过用户确认

## License

Apache-2.0
