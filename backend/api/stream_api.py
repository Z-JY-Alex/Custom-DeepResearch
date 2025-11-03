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

from backend.agent.planner_ai_test import PlanAgent
from backend.agent.search import SearchAgent
from backend.agent.content_analyzer import ContentAnalyzerAgent
from backend.agent.generate_test_cases import TestCasesGeneratorAgent
from backend.agent.code_executor import CodeExecutorAgent
from backend.llm.base import LLMConfig
from backend.memory.base import BaseMemory
from backend.artifacts.manager import ArtifactManager
from backend.interaction.manager import interaction_manager


class StreamEventType(str, Enum):
    """流式事件类型"""
    AGENT_START = "agent_start"           # Agent开始执行
    AGENT_CONTENT = "agent_content"       # Agent普通内容输出
    TOOL_CALL_START = "tool_call_start"   # 工具调用开始
    TOOL_ARGS = "tool_args"               # 工具参数
    TOOL_RESULT_START = "tool_result_start"  # 工具结果开始
    TOOL_RESULT_CONTENT = "tool_result_content"  # 工具结果内容
    TOOL_RESULT_END = "tool_result_end"   # 工具结果结束
    FILE_OPERATION = "file_operation"     # 文件操作事件
    AGENT_ROUND = "agent_round"           # Agent执行轮次信息
    AGENT_FINISHED = "agent_finished"     # Agent执行完成
    ERROR = "error"                       # 错误事件
    HEARTBEAT = "heartbeat"               # 心跳事件
    # 用户交互相关事件
    USER_QUESTION = "user_question"       # AI询问用户
    USER_ANSWER_RECEIVED = "user_answer_received"  # 收到用户回答
    INTERACTION_TIMEOUT = "interaction_timeout"    # 交互超时


class StreamEvent(BaseModel):
    """流式事件数据结构"""
    event_type: StreamEventType = Field(..., description="事件类型")
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="事件ID")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="时间戳")
    
    # 基础数据
    content: Optional[str] = Field(default=None, description="文本内容")
    data: Optional[Dict[str, Any]] = Field(default=None, description="结构化数据")
    
    # Agent信息
    agent_id: Optional[str] = Field(default=None, description="Agent ID")
    agent_name: Optional[str] = Field(default=None, description="Agent名称")
    current_round: Optional[int] = Field(default=None, description="当前执行轮次")
    
    # 工具调用信息
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    tool_call_id: Optional[str] = Field(default=None, description="工具调用ID")
    tool_args: Optional[Dict[str, Any]] = Field(default=None, description="工具参数")
    
    # 文件操作信息
    file_path: Optional[str] = Field(default=None, description="文件路径")
    operation_mode: Optional[str] = Field(default=None, description="操作模式")
    is_streaming_file: Optional[bool] = Field(default=False, description="是否为流式文件操作")
    
    # 状态信息
    token_usage: Optional[Dict[str, Any]] = Field(default=None, description="Token使用情况")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class AgentExecuteRequest(BaseModel):
    """Agent执行请求"""
    query: str = Field(..., description="用户查询")
    agent_type: str = Field(default="PlanAgent", description="Agent类型")
    llm_config: Optional[Dict[str, Any]] = Field(default=None, description="LLM配置")
    max_rounds: Optional[int] = Field(default=80, description="最大执行轮数")
    stream_file_operations: bool = Field(default=True, description="是否启用流式文件操作")


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
        
        # 确保max_tokens不会超过模型限制（65536）
        if "max_tokens" in llm_config and llm_config["max_tokens"] > 65536:
            logger.warning(f"max_tokens ({llm_config['max_tokens']}) 超过模型限制65536，将自动调整为65536")
            llm_config["max_tokens"] = 65536
        
        llm_config_obj = LLMConfig(**llm_config)
        # 验证配置
        if not llm_config_obj.api_key:
            logger.warning(f"LLM配置中的api_key为空，配置对象: {llm_config_obj}")
        memory = BaseMemory()
        artifact_manager = ArtifactManager()
        
        agent_maps = {
            "WEB_SEARCH": SearchAgent,
            "CONTENT_ANALYSIS": ContentAnalyzerAgent,
            "TEST_CASE_GENERATE": TestCasesGeneratorAgent,
            "CODE_GENERATE": CodeExecutorAgent
        }
        
        if agent_type == "PlanAgent":
            agent = PlanAgent(
                llm_config=llm_config_obj,
                agent_maps=agent_maps,
                memory=memory,
                artifact_manager=artifact_manager
            )
            # 设置交互管理器和会话ID
            agent.interaction_manager = interaction_manager
            agent.session_id = session_id
            return agent
        else:
            raise ValueError(f"不支持的Agent类型: {agent_type}")
    
    async def parse_agent_output(self, chunk: str, session_info: Dict[str, Any]) -> AsyncGenerator[StreamEvent, None]:
        """解析Agent输出并转换为结构化事件"""
        agent = session_info["agent"]
        current_state = session_info.get("current_state", "content")
        
        # 检测工具调用开始
        if "<TOOL_CALL>" in chunk:
            tool_name = chunk.split("<TOOL_CALL>")[1].split("</TOOL_CALL>")[0].strip()
            session_info["current_state"] = "tool_call"
            session_info["current_tool"] = tool_name
            
            yield StreamEvent(
                event_type=StreamEventType.TOOL_CALL_START,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=tool_name,
                content=f"开始执行工具: {tool_name}"
            )
            return
        
        # 检测工具参数
        if "<TOOL_ARGS>" in chunk:
            args_content = chunk.split("<TOOL_ARGS>")[1].split("</TOOL_ARGS>")[0].strip()
            try:
                tool_args = json.loads(args_content) if args_content else {}
            except:
                tool_args = {"raw_args": args_content}
            
            # 检查是否为文件操作
            is_file_op = session_info.get("current_tool") == "stream_file_operation"
            file_path = tool_args.get("filepath") if is_file_op else None
            operation_mode = tool_args.get("operation_mode") if is_file_op else None
            
            yield StreamEvent(
                event_type=StreamEventType.TOOL_ARGS,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session_info.get("current_tool"),
                tool_args=tool_args,
                file_path=file_path,
                operation_mode=operation_mode,
                is_streaming_file=is_file_op,
                content=f"工具参数: {args_content[:200]}..."
            )
            return
        
        # 检测工具结果开始
        if "<TOOL_RESULT>" in chunk:
            session_info["current_state"] = "tool_result"
            yield StreamEvent(
                event_type=StreamEventType.TOOL_RESULT_START,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session_info.get("current_tool"),
                content="工具执行结果:"
            )
            return
        
        # 检测工具结果结束
        if "</TOOL_RESULT>" in chunk:
            session_info["current_state"] = "content"
            yield StreamEvent(
                event_type=StreamEventType.TOOL_RESULT_END,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session_info.get("current_tool"),
                content="工具执行完成"
            )
            session_info["current_tool"] = None
            return
        
        # 处理普通内容
        if chunk.strip():
            event_type = StreamEventType.TOOL_RESULT_CONTENT if current_state == "tool_result" else StreamEventType.AGENT_CONTENT
            
            # 检查是否为文件操作内容
            is_file_streaming = (
                current_state == "tool_result" and 
                session_info.get("current_tool") == "stream_file_operation" and
                agent.file_operation_tool and 
                agent.file_operation_tool.is_active()
            )
            
            yield StreamEvent(
                event_type=event_type,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session_info.get("current_tool") if current_state == "tool_result" else None,
                content=chunk,
                is_streaming_file=is_file_streaming,
                file_path=agent.file_operation_tool._filepath.name if is_file_streaming and agent.file_operation_tool._filepath else None,
                operation_mode=agent.file_operation_tool.get_operation_mode() if is_file_streaming else None
            )
    
    async def execute_agent_stream(self, request: AgentExecuteRequest) -> AsyncGenerator[str, None]:
        """执行Agent并返回流式响应"""
        session_id = str(uuid.uuid4())
        
        try:
            # 创建Agent
            llm_config = request.llm_config or {
                "model_name": "MaaS_Sonnet_4",
                "api_key": "amep3rwbqWIpFoOnKpZw",
                "base_url": "https://genaiapish-zy2cw9s.xiaosuai.com/v1",
                "max_tokens": 64000
            }
            
            agent = self.create_agent(request.agent_type, llm_config, session_id)
            if request.max_rounds:
                agent.max_rounds = request.max_rounds
            
            # 初始化会话信息
            session_info = {
                "agent": agent,
                "current_state": "content",
                "current_tool": None,
                "start_time": datetime.now()
            }
            self.active_sessions[session_id] = session_info
            
            # 发送开始事件
            start_event = StreamEvent(
                event_type=StreamEventType.AGENT_START,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=0,
                content=f"开始执行 {request.agent_type}",
                data={"session_id": session_id, "query": request.query}
            )
            yield f"data: {start_event.model_dump_json()}\n\n"
            
            # 执行Agent并处理输出
            async for chunk in agent.run(request.query):
                # 解析输出并生成事件
                async for event in self.parse_agent_output(chunk, session_info):
                    yield f"data: {event.model_dump_json()}\n\n"
                
                # 定期发送轮次信息
                if agent.current_round != session_info.get("last_round", 0):
                    session_info["last_round"] = agent.current_round
                    round_event = StreamEvent(
                        event_type=StreamEventType.AGENT_ROUND,
                        agent_id=agent.agent_id,
                        agent_name=agent.agent_name,
                        current_round=agent.current_round,
                        content=f"执行轮次: {agent.current_round}",
                        token_usage=agent.get_token_usage_info()
                    )
                    yield f"data: {round_event.model_dump_json()}\n\n"
            
            # 发送完成事件
            finish_event = StreamEvent(
                event_type=StreamEventType.AGENT_FINISHED,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                content="Agent执行完成",
                data={
                    "session_id": session_id,
                    "total_rounds": agent.current_round,
                    "execution_time": (datetime.now() - session_info["start_time"]).total_seconds(),
                    "final_state": agent.state.value
                }
            )
            yield f"data: {finish_event.model_dump_json()}\n\n"
            
        except Exception as e:
            logger.error(f"Agent执行失败: {e}")
            error_event = StreamEvent(
                event_type=StreamEventType.ERROR,
                content=f"执行失败: {str(e)}",
                error_message=str(e),
                data={"session_id": session_id}
            )
            yield f"data: {error_event.model_dump_json()}\n\n"
        
        finally:
            # 清理会话
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]


# 创建API实例
app = FastAPI(title="Agent流式执行API", version="1.0.0")
stream_handler = StreamAPIHandler()


@app.post("/api/v1/agent/execute/stream")
async def execute_agent_stream(request: AgentExecuteRequest):
    """
    流式执行Agent
    
    返回Server-Sent Events (SSE)格式的流式响应
    每个事件包含完整的JSON数据，前端可以根据event_type进行不同处理
    """
    return StreamingResponse(
        stream_handler.execute_agent_stream(request),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )


@app.post("/api/v1/agent/user-answer")
async def submit_user_answer(request: UserAnswerRequest):
    """
    接收用户回答
    
    用于用户回答AI的问题，支持文本输入、选择题、确认题等多种回答类型
    """
    try:
        # 验证请求参数
        if not request.answer.strip():
            return {
                "status": "error",
                "message": "回答内容不能为空",
                "interaction_id": request.interaction_id
            }
        
        # 提交用户回答
        success = await interaction_manager.submit_answer(
            request.interaction_id, 
            request.answer
        )
        
        if success:
            logger.info(f"用户回答已提交: {request.interaction_id}, 回答: {request.answer}")
            return {
                "status": "success",
                "message": "回答已提交，AI继续执行中",
                "interaction_id": request.interaction_id,
                "session_id": request.session_id,
                "answer": request.answer,
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.warning(f"交互不存在或已过期: {request.interaction_id}")
            return {
                "status": "error", 
                "message": "交互不存在或已过期，可能已超时",
                "interaction_id": request.interaction_id
            }
            
    except Exception as e:
        logger.error(f"提交用户回答失败: {e}")
        return {
            "status": "error",
            "message": f"提交失败: {str(e)}",
            "interaction_id": request.interaction_id
        }


@app.get("/api/v1/agent/sessions")
async def get_active_sessions():
    """获取活跃会话列表"""
    sessions = []
    for session_id, info in stream_handler.active_sessions.items():
        agent = info["agent"]
        sessions.append({
            "session_id": session_id,
            "agent_id": agent.agent_id,
            "agent_name": agent.agent_name,
            "current_round": agent.current_round,
            "start_time": info["start_time"].isoformat(),
            "current_state": info.get("current_state"),
            "current_tool": info.get("current_tool")
        })
    return {"active_sessions": sessions}


@app.get("/api/v1/agent/interactions/{session_id}")
async def get_session_interactions(session_id: str):
    """获取会话的交互历史"""
    try:
        interactions = await interaction_manager.get_session_interactions(session_id)
        return {
            "status": "success",
            "session_id": session_id,
            "interactions": [interaction.dict() for interaction in interactions],
            "total_count": len(interactions)
        }
    except Exception as e:
        logger.error(f"获取会话交互历史失败: {e}")
        return {
            "status": "error",
            "message": f"获取失败: {str(e)}",
            "session_id": session_id
        }


@app.get("/api/v1/agent/interaction-stats")
async def get_interaction_stats():
    """获取交互统计信息"""
    try:
        stats = interaction_manager.get_stats()
        return {
            "status": "success",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"获取交互统计失败: {e}")
        return {
            "status": "error",
            "message": f"获取统计失败: {str(e)}"
        }


@app.get("/api/v1/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
