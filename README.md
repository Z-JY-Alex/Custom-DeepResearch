# Deep Research

基于多Agent协作的深度研究助手，支持自动规划、并行执行、流式输出的智能研究系统。

## 功能特性

- **智能规划**：PlanAgent 自动拆解复杂任务为多个子步骤
- **并行执行**：多个子任务并行运行，实时流式输出进度
- **多Agent协作**：搜索、内容分析、数据分析、代码生成、测试用例生成等专业Agent
- **流式文件操作**：实时查看文件写入过程
- **产出物管理**：自动收集和管理研究过程中的产出文件
- **会话管理**：支持多轮对话和会话复用

## 项目结构

```
deepresearch/
├── backend/
│   ├── api/
│   │   └── stream_api.py          # 主API入口（流式SSE）
│   ├── agent/
│   │   ├── general_agent/         # Agent实现
│   │   │   ├── base.py            # Agent基类
│   │   │   ├── planner.py         # 规划Agent（任务拆解与并行调度）
│   │   │   ├── search.py          # 搜索Agent
│   │   │   ├── content_analyzer.py# 内容分析Agent
│   │   │   ├── summary.py         # 总结Agent
│   │   │   └── data_analysis.py   # 数据分析Agent
│   │   ├── code_executor.py       # 代码执行Agent
│   │   ├── generate_test_cases.py # 测试用例生成Agent
│   │   └── schema.py              # 数据模型
│   ├── llm/
│   │   ├── base.py                # LLM配置与消息模型
│   │   ├── llm.py                 # OpenAI客户端封装
│   │   └── token_counter.py       # Token计数
│   ├── tools/                     # 工具集
│   │   ├── tavily_search.py       # Tavily搜索
│   │   ├── stream_file_operations.py # 流式文件读写
│   │   ├── code_execute.py        # 代码执行（沙箱）
│   │   ├── shell_execute.py       # Shell命令执行
│   │   ├── plan.py                # 计划管理工具
│   │   └── ...
│   ├── prompts/                   # Agent提示词
│   ├── memory/                    # 记忆管理
│   ├── artifacts/                 # 产出物管理
│   ├── mcp_client/                # MCP协议客户端
│   └── config.py                  # 集中配置管理
├── frontend/
│   ├── index.html                 # 前端页面
│   ├── app.js                     # 前端逻辑（SSE流式处理）
│   └── server.py                  # 前端静态文件服务
├── .env.example                   # 环境变量模板
├── .env                           # 环境变量配置（不提交）
└── requirements.txt               # Python依赖
```

## 快速开始

### 1. 环境准备

```bash
# Python 3.10+
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入实际配置：

```env
# LLM 配置（必填）
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://your-api-base-url/v1
DEFAULT_MODEL_NAME=MaaS_Sonnet_4

# 搜索配置（必填）
TAVILY_API_KEY=your_tavily_api_key

# 可选配置
DEFAULT_MAX_TOKENS=32000
LLM_TEMPERATURE=0.7
SERVER_HOST=0.0.0.0
SERVER_PORT=1234
```

完整配置项参见 `.env.example`。

### 3. 启动服务

```bash
# 启动后端API（默认端口 1234）
python -m backend.api.stream_api

# 启动前端页面（另开终端）
cd frontend
python server.py
```

浏览器打开前端页面即可使用。

## Agent 类型

| Agent | 说明 |
|-------|------|
| `PlanAgent` | 主Agent，负责任务规划和子Agent调度 |
| `WEB_SEARCH` | 网络搜索，使用Tavily API |
| `CONTENT_ANALYSIS` | 文档内容深度分析 |
| `DATA_ANALYSIS` | 数据分析与可视化 |
| `CODE_GENERATE` | 代码生成与执行 |
| `TEST_CASE_GENERATE` | 测试用例自动生成 |
| `SUMMARY_REPORT` | 汇总所有子任务结果生成最终报告 |

## API 接口

### POST `/api/agent/execute`

流式执行Agent任务，返回SSE事件流。

**请求体：**

```json
{
  "query": "研究问题描述",
  "agent_type": "PlanAgent",
  "max_rounds": 80,
  "session_id": null
}
```

**SSE事件类型：**

| 事件 | 说明 |
|------|------|
| `AGENT_CONTENT` | Agent输出内容（支持并行流式） |
| `TOOL_CALL_START` | 工具调用开始 |
| `TOOL_ARGS` | 工具参数 |
| `TOOL_RESULT_START/END` | 工具执行结果 |
| `PLAN_UPDATE` | 计划更新 |
| `AGENT_FINISHED` | 执行完成 |

### POST `/api/agent/answer`

用户回答Agent提出的交互问题。

## 技术栈

- **后端**: Python, FastAPI, OpenAI API, Tavily
- **前端**: 原生JS, SSE (Server-Sent Events), Markdown渲染
- **协议**: MCP (Model Context Protocol)

## License

MIT
