"""
流式API接口模块：提供Agent执行的流式HTTP接口
支持实时工具调用、文件操作和状态监控
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import json
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger
import traceback
import os
from backend import config

# 配置日志：保存到 logs/ 文件夹
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

# 移除默认的控制台处理器（如果需要）
logger.remove()

# 添加控制台输出（使用格式化）
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 添加文件输出：按日期轮转
logger.add(
    logs_dir / "stream_api_{time:YYYY-MM-DD}.log",
    rotation="00:00",  # 每天午夜轮转
    retention="30 days",  # 保留30天
    compression="zip",  # 压缩旧日志
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="INFO",
    encoding="utf-8"
)

# from backend.agent.planner_ai_test import PlanAgent
from backend.agent.general_agent.planner import PlanAgent
from backend.agent.general_agent.search import SearchAgent
from backend.agent.general_agent.content_analyzer import ContentAnalyzerAgent
from backend.agent.generate_test_cases import TestCasesGeneratorAgent
from backend.agent.code_executor import CodeExecutorAgent
from backend.agent.general_agent.data_analysis import DataAnalysisAgent

from backend.llm.base import LLMConfig, Message, MessageRole
from backend.memory.base import BaseMemory
from backend.artifacts.manager import ArtifactManager
from backend.agent.general_agent.base import AgentStreamPayload, AgentEventType
from backend.agent.general_agent.summary import SummaryAgent
from backend.agent.schema import AgentState


class AgentExecuteRequest(BaseModel):
    """Agent执行请求"""
    query: str = Field(..., description="用户查询")
    agent_type: str = Field(default="PlanAgent", description="Agent类型")
    llm_config: Optional[Dict[str, Any]] = Field(default=None, description="LLM配置")
    max_rounds: Optional[int] = Field(default=80, description="最大执行轮数")
    stream_file_operations: bool = Field(default=True, description="是否启用流式文件操作")
    session_id: Optional[str] = Field(default=None, description="复用会话ID（如为空则新建会话）")


class UserAnswerRequest(BaseModel):
    """用户回答请求"""
    session_id: str = Field(..., description="会话ID")
    interaction_id: str = Field(..., description="交互ID")
    answer: str = Field(..., description="用户回答")
    answer_type: str = Field(default="text", description="回答类型：text/choice/confirm")


class StreamAPIHandler:
    """流式API处理器"""
    
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
    def create_agent(self, agent_type: str, llm_config: Dict[str, Any], session_id: str) -> Any:
        """创建Agent实例"""
        # 确保配置中有必要的字段
        logger.debug(f"创建Agent，配置: {llm_config}")
        
        llm_config_obj = LLMConfig(**llm_config)
        # 验证配置
        if not llm_config_obj.api_key:
            logger.warning(f"LLM配置中的api_key为空，配置对象: {llm_config_obj}")
        memory = BaseMemory()
        artifact_manager = ArtifactManager(session_id=session_id)
        
        agent_maps = {
            "WEB_SEARCH": SearchAgent,
            "CONTENT_ANALYSIS": ContentAnalyzerAgent,
            "TEST_CASE_GENERATE": TestCasesGeneratorAgent,
            "CODE_GENERATE": CodeExecutorAgent,
            "SUMMARY_REPORT": SummaryAgent,
            "DATA_ANALYSIS": DataAnalysisAgent
        }
        
        if agent_type == "PlanAgent":
            agent = PlanAgent(
                llm_config=llm_config_obj,
                agent_maps=agent_maps,
                memory=memory,
                artifact_manager=artifact_manager,
                session_id=session_id
            )
            
            return agent
        else:
            raise ValueError(f"不支持的Agent类型: {agent_type}")
    
    
    async def execute_agent_stream(self, request: AgentExecuteRequest) -> AsyncGenerator[str, None]:
        """执行Agent并返回流式响应"""
        # 如果传入了session_id且会话存在，则复用；否则新建会话
        session_id = request.session_id or str(uuid.uuid4())
        
        try:
            # 确定Agent与消息历史
            if request.session_id and request.session_id in self.active_sessions:
                # 复用已有会话
                logger.info(f"[会话] 复用已有会话: {session_id}")
                session_info = self.active_sessions[session_id]
                agent = session_info["agent"]
                # 从agent内存中取历史
                try:
                    history_messages = agent.memory.states.get(agent.agent_id, {}).get("all_history", [])
                except Exception:
                    history_messages = []
                # 追加当前用户输入
                history_messages = list(history_messages)
                history_messages.append(
                    Message(
                        role=MessageRole.USER,
                        content=request.query,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        metadata={"current_round": agent.current_round}
                    )
                )
                messages_to_run = history_messages
                logger.info(f"[会话] 用户输入: {request.query[:100]}{'...' if len(request.query) > 100 else ''}")
            else:
                # 新建会话与Agent
                logger.info(f"[会话] 创建新会话: {session_id}, Agent类型: {request.agent_type}")
                llm_config = config.get_llm_config()
                agent = self.create_agent(request.agent_type, llm_config, session_id)
                if request.max_rounds:
                    agent.max_rounds = request.max_rounds
                # 构造首条用户消息
                messages_to_run = [
                    Message(
                        role=MessageRole.USER ,
                        content=request.query + f"当前时间： {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        metadata={"current_round": agent.current_round}
                    )
                ]
                # 初始化会话信息
                session_info = {
                    "agent": agent,
                    "current_state": "content",
                    "current_tool": None,
                    "start_time": datetime.now()
                }
                self.active_sessions[session_id] = session_info
                logger.info(f"[会话] 用户查询: {request.query[:100]}{'...' if len(request.query) > 100 else ''}")
            
            logger.info(f"[流式执行] 开始执行Agent，轮次限制: {agent.max_rounds}")
            
            # 直接透传Agent的JSON事件
            async for chunk in agent.run(messages_to_run):
                # 控制台输出：简洁可读的连续文本
                try:
                    event_data = json.loads(chunk)
                    event_type = event_data.get("event_type", "unknown")
                    tool_name = event_data.get("tool", {}).get("name") if isinstance(event_data.get("tool"), dict) else None
                    content = event_data.get("content", "")
                    current_round = event_data.get("current_round")

                    if event_type == "agent_content":
                        pass  # base.py 已通过 print(content, end="") 输出连续文本
                    elif event_type == "tool_call_start":
                        sys.stdout.write(f"\n🔧 [{tool_name}] ")
                        sys.stdout.flush()
                    elif event_type == "tool_result_content":
                        pass  # 工具结果不在控制台显示
                    elif event_type == "tool_result_end":
                        sys.stdout.write(f"✅\n")
                        sys.stdout.flush()
                    elif event_type == "agent_running":
                        sys.stdout.write(f"\n--- 轮次 {current_round} ---\n")
                        sys.stdout.flush()
                    elif event_type == "agent_finished":
                        sys.stdout.write(f"\n✅ Agent 执行完成\n")
                        sys.stdout.flush()
                    elif event_type == "error":
                        error_msg = event_data.get("error_message", "")
                        logger.error(f"[错误] {error_msg}")
                    elif event_type == "ask_user":
                        sys.stdout.write(f"\n❓ {content}\n")
                        sys.stdout.flush()
                except json.JSONDecodeError:
                    pass

                yield f"data: {chunk}\n\n"
            
            # 流式执行完成
            execution_time = (datetime.now() - session_info["start_time"]).total_seconds()
            logger.info(f"[流式执行] Agent执行完成，会话: {session_id}, 耗时: {execution_time:.2f}秒")
            
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[错误] Agent执行失败: {str(e)}")
            logger.error(f"[错误] Traceback:\n{tb}")
            error_event = AgentStreamPayload(
                event_type=AgentEventType.ERROR,
                agent_id=None,
                agent_name=None,
                session_id=session_id,
                current_round=None,
                error_message=str(e),
                data={"session_id": session_id, "traceback": tb}
            )
            logger.info(f"[流式输出] 错误事件已发送")
            yield f"data: {error_event.to_json()}\n\n"
        

# 创建API实例
app = FastAPI(title="Agent流式执行API", version="1.0.0")
stream_handler = StreamAPIHandler()

# 添加 CORS 中间件支持（如果需要）
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/v1/agent/stream")
async def api_agent_stream(request: AgentExecuteRequest):
    """启动Agent流式执行，SSE输出Agent的统一JSON事件"""
    generator = stream_handler.execute_agent_stream(request)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.post("/api/v1/agent/answer")
async def api_submit_user_answer(request: UserAnswerRequest):
    """
    提交用户回答，恢复Agent执行

    Args:
        request: 用户回答请求，包含 session_id, interaction_id, answer

    Returns:
        StreamingResponse: 继续流式输出Agent的后续执行结果
    """
    try:
        # 验证会话是否存在
        if request.session_id not in stream_handler.active_sessions:
            raise HTTPException(
                status_code=404,
                detail=f"会话不存在: {request.session_id}"
            )

        session_info = stream_handler.active_sessions[request.session_id]
        agent = session_info["agent"]

        # 验证Agent状态
        if agent.state != AgentState.WAITING_USER_INPUT:
            raise HTTPException(
                status_code=400,
                detail=f"Agent当前状态不是等待用户输入: {agent.state}"
            )

        # 处理用户回答
        success = agent.handle_user_answer(request.interaction_id, request.answer)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"处理用户回答失败: interaction_id={request.interaction_id}"
            )

        logger.info(f"[用户回答] 会话: {request.session_id}, 交互ID: {request.interaction_id}, 回答: {request.answer[:50]}")

        # 创建一个新的请求对象继续执行
        continue_request = AgentExecuteRequest(
            query=request.answer,
            agent_type="PlanAgent",
            session_id=request.session_id
        )

        # 继续流式执行Agent
        generator = stream_handler.execute_agent_stream(continue_request)
        return StreamingResponse(generator, media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[错误] 处理用户回答失败: {str(e)}\n{tb}")
        raise HTTPException(status_code=500, detail=f"处理用户回答失败: {str(e)}")


@app.get("/api/v1/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/v1/file/list")
async def list_files(session_id: str):
    """列出session下的所有文件"""
    try:
        # 安全检查：确保session_id不包含危险字符
        if ".." in session_id or "/" in session_id or "\\" in session_id:
            raise HTTPException(status_code=400, detail="Invalid session_id")

        # 构建session目录路径
        session_dir = project_root / session_id

        # 检查目录是否存在
        if not session_dir.exists():
            return {
                "status": "success",
                "session_id": session_id,
                "files": []
            }

        if not session_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Not a directory: {session_id}")

        # 递归扫描所有文件
        files = []
        for file_path in session_dir.rglob('*'):
            if file_path.is_file():
                try:
                    # 获取相对路径
                    relative_path = file_path.relative_to(project_root)
                    stat = file_path.stat()

                    files.append({
                        "name": file_path.name,
                        "path": str(relative_path).replace('\\', '/'),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception as e:
                    logger.warning(f"无法获取文件信息: {file_path}, 错误: {str(e)}")
                    continue

        # 按修改时间排序（最新的在前）
        files.sort(key=lambda x: x['modified'], reverse=True)

        logger.info(f"成功列出session文件: {session_id}, 文件数: {len(files)}")

        return {
            "status": "success",
            "session_id": session_id,
            "files": files,
            "count": len(files)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"列出文件失败: {session_id}, 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@app.get("/api/v1/file/read")
async def read_file(filepath: str):
    """读取文件内容"""
    try:
        # 安全检查：确保路径不包含 ../ 等危险字符
        if ".." in filepath or filepath.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")

        # 构建完整路径（相对于项目根目录）
        full_path = project_root / filepath

        # 检查文件是否存在
        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filepath}")

        # 检查是否是文件
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {filepath}")

        # 读取文件内容
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        logger.info(f"成功读取文件: {filepath}, 大小: {len(content)} 字符")

        return {
            "status": "success",
            "filepath": filepath,
            "content": content,
            "size": len(content)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"读取文件失败: {filepath}, 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    server_cfg = config.get_server_config()
    uvicorn.run(app, host=server_cfg["host"], port=server_cfg["port"])
