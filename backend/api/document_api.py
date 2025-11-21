"""
接口文档上传处理API：支持用户上传接口文档并返回流式分析结果
支持并发处理、文件上传和实时状态监控
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
import tempfile
import os
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator, List
from enum import Enum
import aiofiles
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from loguru import logger
import traceback

# 配置 loguru 日志级别为 INFO
logger.remove()  # 移除默认的处理器
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

from backend.agent.planner_ai_test import PlanAgent
from backend.agent.search import SearchAgent
from backend.agent.content_analyzer import ContentAnalyzerAgent
from backend.agent.generate_test_cases import TestCasesGeneratorAgent
from backend.agent.code_executor import CodeExecutorAgent
from backend.llm.base import LLMConfig
from backend.memory.base import BaseMemory
from backend.artifacts.manager import ArtifactManager
from backend.interaction.manager import interaction_manager


class DocumentProcessStatus(str, Enum):
    """文档处理状态"""
    UPLOADING = "uploading"           # 上传中
    UPLOADED = "uploaded"             # 上传完成
    PROCESSING = "processing"         # 处理中
    COMPLETED = "completed"           # 处理完成
    ERROR = "error"                   # 处理错误
    CANCELLED = "cancelled"           # 已取消


class StreamEventType(str, Enum):
    """流式事件类型"""
    UPLOAD_START = "upload_start"         # 上传开始
    UPLOAD_PROGRESS = "upload_progress"   # 上传进度
    UPLOAD_COMPLETE = "upload_complete"   # 上传完成
    AGENT_START = "agent_start"           # Agent开始执行
    AGENT_CONTENT = "agent_content"       # Agent普通内容输出
    TOOL_CALL_START = "tool_call_start"   # 工具调用开始
    TOOL_ARGS = "tool_args"               # 工具参数
    TOOL_RESULT_START = "tool_result_start"  # 工具结果开始
    TOOL_RESULT_CONTENT = "tool_result_content"  # 工具结果内容
    TOOL_RESULT_END = "tool_result_end"   # 工具结果结束
    AGENT_ROUND = "agent_round"           # Agent执行轮次信息
    AGENT_FINISHED = "agent_finished"     # Agent执行完成
    ERROR = "error"                       # 错误事件
    HEARTBEAT = "heartbeat"               # 心跳事件


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
    
    # 处理进度信息
    progress: Optional[float] = Field(default=None, description="处理进度(0-100)")
    status: Optional[DocumentProcessStatus] = Field(default=None, description="处理状态")
    
    # 状态信息
    token_usage: Optional[Dict[str, Any]] = Field(default=None, description="Token使用情况")
    error_message: Optional[str] = Field(default=None, description="错误信息")


class DocumentUploadRequest(BaseModel):
    """文档上传请求"""
    agent_type: str = Field(default="PlanAgent", description="Agent类型")
    max_rounds: Optional[int] = Field(default=80, description="最大执行轮数")
    custom_prompt: Optional[str] = Field(default=None, description="自定义提示词")
    priority: Optional[int] = Field(default=1, description="处理优先级(1-10)")


class DocumentProcessSession:
    """文档处理会话"""
    def __init__(self, session_id: str, file_path: str, request: DocumentUploadRequest):
        self.session_id = session_id
        self.file_path = file_path
        self.request = request
        self.status = DocumentProcessStatus.UPLOADED
        self.agent = None
        self.start_time = datetime.now()
        self.current_state = "content"
        self.current_tool = None
        self.error_message = None
        self.progress = 0.0
        self.session_logger = None  # 专属logger
        self.log_file_path = None   # 日志文件路径
        self.log_handler_id = None  # 日志handler ID
        self.task: Optional[asyncio.Task] = None  # 后台处理任务引用


class ConcurrentDocumentHandler:
    """并发文档处理器"""
    
    def __init__(self, max_concurrent_sessions: int = 10, max_workers: int = 4):
        self.max_concurrent_sessions = max_concurrent_sessions
        self.max_workers = max_workers
        self.active_sessions: Dict[str, DocumentProcessSession] = {}
        self.session_queues: Dict[str, asyncio.Queue] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.semaphore = asyncio.Semaphore(max_concurrent_sessions)
        self.active_tasks: Dict[str, asyncio.Task] = {}  # 跟踪活跃任务
    
    def create_session_logger(self, session_id: str, work_dir: str):
        """为session创建专属的logger"""
        # 创建日志目录
        log_dir = os.path.join(work_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # 日志文件路径
        log_file_path = os.path.join(log_dir, f"session_{session_id}.log")
        
        # 创建专属logger，绑定session_id用于在消息中显示
        session_logger = logger.bind(session_id=session_id)
        
        # 添加文件handler，使用与test_plan_agent_ai_test.py相同的格式
        handler_id = logger.add(
            log_file_path,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="INFO",
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8"
        )
        
        return session_logger, log_file_path, handler_id
        
    async def cleanup_session(self, session_id: str):
        """清理会话资源"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            
            # 记录清理开始（使用session专属logger）
            if session.session_logger:
                session.session_logger.info(f"[{session_id}] 开始清理会话")
            
            # 清理logger handler
            if session.log_handler_id is not None:
                try:
                    logger.remove(session.log_handler_id)
                    if session.session_logger:
                        session.session_logger.info(f"[{session_id}] 已移除日志handler")
                except Exception as e:
                    logger.warning(f"移除日志handler失败: {e}\n{traceback.format_exc()}")
            
            # 清理Agent的工作目录
            if session.agent and hasattr(session.agent, 'cleanup_session_directory'):
                try:
                    session.agent.cleanup_session_directory()
                    if session.session_logger:
                        session.session_logger.info(f"[{session_id}] 已清理Agent工作目录")
                except Exception as e:
                    error_msg = f"[{session_id}] 清理Agent工作目录失败: {e}"
                    tb = traceback.format_exc()
                    if session.session_logger:
                        session.session_logger.warning(f"{error_msg}\n{tb}")
                    else:
                        logger.warning(f"{error_msg}\n{tb}")
            
            # 删除临时文件
            try:
                if os.path.exists(session.file_path):
                    os.remove(session.file_path)
                    if session.session_logger:
                        session.session_logger.info(f"[{session_id}] 已删除临时文件: {session.file_path}")
            except Exception as e:
                error_msg = f"[{session_id}] 删除临时文件失败: {e}"
                tb = traceback.format_exc()
                if session.session_logger:
                    session.session_logger.warning(f"{error_msg}\n{tb}")
                else:
                    logger.warning(f"{error_msg}\n{tb}")
            
            # 最后记录清理完成
            if session.session_logger:
                session.session_logger.info(f"[{session_id}] 会话清理完成")
            
            # 清理会话数据
            del self.active_sessions[session_id]
            if session_id in self.session_queues:
                del self.session_queues[session_id]
            
            logger.info(f"会话 {session_id} 已清理")
    
    def create_agent(self, agent_type: str, session_id: str) -> Any:
        """创建Agent实例"""
        llm_config = LLMConfig(
            model_name="MaaS_Opus_4",
            api_key="amep3rwbqWIpFoOnKpZw",
            base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1",
            max_tokens=32000
        )
        
        memory = BaseMemory(compression_llm_config=llm_config)
        artifact_manager = ArtifactManager(storage_path=f"{session_id}/artifacts")
        
        agent_maps = {
            "WEB_SEARCH": SearchAgent,
            "CONTENT_ANALYSIS": ContentAnalyzerAgent,
            "TEST_CASE_GENERATE": TestCasesGeneratorAgent,
            "CODE_GENERATE": CodeExecutorAgent
        }
        
        if agent_type == "PlanAgent":
            agent = PlanAgent(
                session_id=session_id,  # 传递session_id用于创建专属工作目录
                llm_config=llm_config,
                agent_maps=agent_maps,
                memory=memory,
                artifact_manager=artifact_manager,
                interaction_manager=interaction_manager
            )
            
            # 为session创建专属logger
            session_logger, log_file_path, handler_id = self.create_session_logger(session_id, agent.work_dir)
            
            # 记录Agent创建信息
            session_logger.info(f"[{session_id}] 已创建PlanAgent，工作目录: {agent.work_dir}")
            logger.info(f"已为会话 {session_id} 创建PlanAgent，工作目录: {agent.work_dir}")
            
            return agent, session_logger, log_file_path, handler_id
        else:
            raise ValueError(f"不支持的Agent类型: {agent_type}")
    
    async def save_uploaded_file(self, file: UploadFile, session_logger=None) -> str:
        """保存上传的文件到临时目录"""
        # 创建临时文件
        temp_dir = tempfile.gettempdir()
        file_extension = os.path.splitext(file.filename)[1] if file.filename else '.txt'
        temp_file_path = os.path.join(temp_dir, f"doc_{uuid.uuid4().hex}{file_extension}")
        
        # 异步保存文件
        async with aiofiles.open(temp_file_path, 'wb') as temp_file:
            content = await file.read()
            await temp_file.write(content)
        
        log_msg = f"文件已保存到: {temp_file_path}, 大小: {len(content)} bytes"
        if session_logger:
            session_logger.info(log_msg)
        logger.info(log_msg)
        return temp_file_path
    
    async def read_document_content(self, file_path: str) -> str:
        """读取文档内容"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            return content
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                async with aiofiles.open(file_path, 'r', encoding='gbk') as f:
                    content = await f.read()
                return content
            except:
                raise HTTPException(status_code=400, detail="无法读取文件内容，请确保文件编码为UTF-8或GBK")
    
    async def parse_agent_output(self, chunk: Any, session: DocumentProcessSession) -> AsyncGenerator[StreamEvent, None]:
        """解析Agent输出并转换为结构化事件"""
        agent = session.agent
        current_state = session.current_state
        
        # 兼容非字符串类型的chunk（例如对象/模型），尽量序列化为字符串
        if isinstance(chunk, bytes):
            try:
                chunk = chunk.decode('utf-8', errors='ignore')
            except Exception:
                chunk = str(chunk)
        elif not isinstance(chunk, str):
            try:
                # 优先尝试常见序列化方式
                if hasattr(chunk, 'model_dump_json'):
                    chunk = chunk.model_dump_json()
                elif hasattr(chunk, 'model_dump'):
                    chunk = json.dumps(chunk.model_dump(), ensure_ascii=False)
                elif hasattr(chunk, 'dict'):
                    chunk = json.dumps(chunk.dict(), ensure_ascii=False)
                elif hasattr(chunk, 'to_json'):
                    chunk = chunk.to_json()
                elif hasattr(chunk, 'text'):
                    chunk = str(getattr(chunk, 'text'))
                elif isinstance(chunk, dict):
                    chunk = json.dumps(chunk, ensure_ascii=False)
                else:
                    chunk = str(chunk)
            except Exception:
                chunk = str(chunk)
        
        # 检测工具调用开始
        if "<TOOL_CALL>" in chunk:
            tool_name = chunk.split("<TOOL_CALL>")[1].split("</TOOL_CALL>")[0].strip()
            session.current_state = "tool_call"
            session.current_tool = tool_name
            
            yield StreamEvent(
                event_type=StreamEventType.TOOL_CALL_START,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=tool_name,
                content=f"开始执行工具: {tool_name}",
                data={"session_id": session.session_id}
            )
            return
        
        # 检测工具参数
        if "<TOOL_ARGS>" in chunk:
            args_content = chunk.split("<TOOL_ARGS>")[1].split("</TOOL_ARGS>")[0].strip()
            try:
                tool_args = json.loads(args_content) if args_content else {}
            except:
                tool_args = {"raw_args": args_content}
            
            yield StreamEvent(
                event_type=StreamEventType.TOOL_ARGS,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session.current_tool,
                tool_args=tool_args,
                content=f"工具参数: {args_content[:200]}...",
                data={"session_id": session.session_id}
            )
            return
        
        # 检测工具结果开始
        if "<TOOL_RESULT>" in chunk:
            session.current_state = "tool_result"
            yield StreamEvent(
                event_type=StreamEventType.TOOL_RESULT_START,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session.current_tool,
                content="工具执行结果:",
                data={"session_id": session.session_id}
            )
            return
        
        # 检测工具结果结束
        if "</TOOL_RESULT>" in chunk:
            session.current_state = "content"
            yield StreamEvent(
                event_type=StreamEventType.TOOL_RESULT_END,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session.current_tool,
                content="工具执行完成",
                data={"session_id": session.session_id}
            )
            session.current_tool = None
            return
        
        # 处理普通内容
        if chunk.strip():
            event_type = StreamEventType.TOOL_RESULT_CONTENT if current_state == "tool_result" else StreamEventType.AGENT_CONTENT
            
            yield StreamEvent(
                event_type=event_type,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                current_round=agent.current_round,
                tool_name=session.current_tool if current_state == "tool_result" else None,
                content=chunk,
                data={"session_id": session.session_id}
            )
    
    async def process_document_stream(self, session_id: str) -> AsyncGenerator[str, None]:
        """处理文档并返回流式响应"""
        session = self.active_sessions.get(session_id)
        if not session:
            error_event = StreamEvent(
                event_type=StreamEventType.ERROR,
                content="会话不存在",
                error_message="Session not found",
                data={"session_id": session_id}
            )
            yield f"data: {error_event.model_dump_json()}\n\n"
            return
        
        async with self.semaphore:  # 控制并发数量
            try:
                # 读取文档内容
                document_content = await self.read_document_content(session.file_path)
                
                # 创建Agent和session logger
                agent_result = self.create_agent(session.request.agent_type, session_id)
                session.agent, session.session_logger, session.log_file_path, session.log_handler_id = agent_result
                if session.request.max_rounds:
                    session.agent.max_rounds = session.request.max_rounds
                
                session.status = DocumentProcessStatus.PROCESSING
                
                # 记录处理开始
                session.session_logger.info(f"[{session_id}] 开始处理接口文档，文档大小: {len(document_content)} 字符")
                session.session_logger.info(f"[{session_id}] Agent类型: {session.request.agent_type}, 最大轮数: {session.request.max_rounds}")
                
                # 发送开始事件
                work_directory = getattr(session.agent, "work_dir", "未知")
                start_event = StreamEvent(
                    event_type=StreamEventType.AGENT_START,
                    agent_id=session.agent.agent_id,
                    agent_name=session.agent.agent_name,
                    current_round=0,
                    content=f"开始处理接口文档 ({len(document_content)} 字符)\n工作目录: {work_directory}",
                    status=session.status,
                    data={
                        "session_id": session_id,
                        "document_size": len(document_content),
                        "agent_type": session.request.agent_type,
                        "work_directory": work_directory,
                        "log_file": session.log_file_path
                    }
                )
                yield f"data: {start_event.model_dump_json()}\n\n"
                
                # 构建查询内容
                query = document_content
                if session.request.custom_prompt:
                    query = f"{session.request.custom_prompt}\n\n接口文档内容：\n{document_content}"
                
                # 执行Agent并处理输出
                async for chunk in session.agent.run(query):
                    # 检查是否被取消
                    if session.status == DocumentProcessStatus.CANCELLED:
                        if session.session_logger:
                            session.session_logger.info(f"[{session_id}] 检测到取消请求，停止处理")
                        # 尝试停止Agent
                        if session.agent and hasattr(session.agent, 'state'):
                            try:
                                from backend.agent.schema import AgentState
                                session.agent.state = AgentState.ERROR
                            except:
                                pass
                        break
                    
                    # 解析输出并生成事件
                    async for event in self.parse_agent_output(chunk, session):
                        yield f"data: {event.model_dump_json()}\n\n"
                    
                    # 定期发送轮次信息和进度更新
                    if session.agent.current_round != session.progress:
                        session.progress = min(session.agent.current_round * 10, 90)  # 简单的进度计算
                        round_event = StreamEvent(
                            event_type=StreamEventType.AGENT_ROUND,
                            agent_id=session.agent.agent_id,
                            agent_name=session.agent.agent_name,
                            current_round=session.agent.current_round,
                            content=f"执行轮次: {session.agent.current_round}",
                            progress=session.progress,
                            status=session.status,
                            token_usage=session.agent.get_token_usage_info() if hasattr(session.agent, 'get_token_usage_info') else None,
                            data={"session_id": session_id}
                        )
                        yield f"data: {round_event.model_dump_json()}\n\n"
                
                # 如果被取消，发送取消事件并提前返回
                if session.status == DocumentProcessStatus.CANCELLED:
                    cancel_event = StreamEvent(
                        event_type=StreamEventType.AGENT_FINISHED,
                        agent_id=session.agent.agent_id if session.agent else None,
                        agent_name=session.agent.agent_name if session.agent else None,
                        current_round=session.agent.current_round if session.agent else 0,
                        content="任务已被取消",
                        progress=session.progress,
                        status=session.status,
                        data={
                            "session_id": session_id,
                            "cancelled": True
                        }
                    )
                    yield f"data: {cancel_event.model_dump_json()}\n\n"
                    return
                
                # 发送完成事件
                session.status = DocumentProcessStatus.COMPLETED
                session.progress = 100.0
                execution_time = (datetime.now() - session.start_time).total_seconds()
                
                # 记录处理完成
                session.session_logger.info(f"[{session_id}] 接口文档处理完成，总轮数: {session.agent.current_round}, 执行时间: {execution_time:.2f}秒")
                
                finish_event = StreamEvent(
                    event_type=StreamEventType.AGENT_FINISHED,
                    agent_id=session.agent.agent_id,
                    agent_name=session.agent.agent_name,
                    current_round=session.agent.current_round,
                    content="接口文档处理完成",
                    progress=session.progress,
                    status=session.status,
                    data={
                        "session_id": session_id,
                        "total_rounds": session.agent.current_round,
                        "execution_time": execution_time,
                        "final_state": session.agent.state.value if hasattr(session.agent, 'state') else "completed",
                        "log_file": session.log_file_path
                    }
                )
                yield f"data: {finish_event.model_dump_json()}\n\n"
                
            except Exception as e:
                error_msg = f"文档处理失败: {e}"
                tb = traceback.format_exc()
                logger.error(f"{error_msg}\n{tb}")
                
                # 使用session logger记录错误
                if session.session_logger:
                    session.session_logger.error(f"[{session_id}] {error_msg}\n{tb}")
                
                session.status = DocumentProcessStatus.ERROR
                session.error_message = str(e)
                error_event = StreamEvent(
                    event_type=StreamEventType.ERROR,
                    content=f"处理失败: {str(e)}",
                    error_message=str(e),
                    status=session.status,
                    data={
                        "session_id": session_id,
                        "log_file": session.log_file_path if session.log_file_path else None
                    }
                )
                yield f"data: {error_event.model_dump_json()}\n\n"


# 创建API实例
app = FastAPI(title="接口文档处理API", version="1.0.0")
document_handler = ConcurrentDocumentHandler(max_concurrent_sessions=20, max_workers=8)

# 添加 CORS 中间件支持
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def start_document_processing_task(session_id: str):
    """后台任务：开始文档处理"""
    session = None
    try:
        # 检查session是否存在
        if session_id not in document_handler.active_sessions:
            logger.warning(f"会话 {session_id} 不存在，任务取消")
            return
        
        session = document_handler.active_sessions[session_id]
        
        # 直接调用处理流程，但不返回流式响应
        async for _ in document_handler.process_document_stream(session_id):
            # 在后台执行，不需要处理流式输出
            # 检查是否被取消
            if session.status == DocumentProcessStatus.CANCELLED:
                if session.session_logger:
                    session.session_logger.info(f"[{session_id}] 后台任务检测到取消请求")
                break
    except asyncio.CancelledError:
        # 任务被取消
        if session_id in document_handler.active_sessions:
            session = document_handler.active_sessions[session_id]
            session.status = DocumentProcessStatus.CANCELLED
            if session.session_logger:
                session.session_logger.info(f"[{session_id}] 后台任务已被取消")
            logger.info(f"会话 {session_id} 的后台任务已被取消")
        raise  # 重新抛出CancelledError
    except Exception as e:
        error_msg = f"后台处理任务失败 (session_id: {session_id}): {e}"
        tb = traceback.format_exc()
        logger.error(f"{error_msg}\n{tb}")
        
        # 更新会话状态为错误
        if session_id in document_handler.active_sessions:
            session = document_handler.active_sessions[session_id]
            session.status = DocumentProcessStatus.ERROR
            session.error_message = str(e)
            
            # 使用session logger记录错误
            if session.session_logger:
                session.session_logger.error(f"[{session_id}] {error_msg}\n{tb}")
    finally:
        # 从活跃任务中移除
        if session_id in document_handler.active_tasks:
            del document_handler.active_tasks[session_id]
        if session and session.task:
            session.task = None


@app.post("/api/v1/document/upload-and-process")
async def upload_and_process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="接口文档文件"),
    agent_type: str = Form(default="PlanAgent", description="Agent类型"),
    max_rounds: Optional[int] = Form(default=80, description="最大执行轮数"),
    custom_prompt: Optional[str] = Form(default=None, description="自定义提示词"),
    priority: Optional[int] = Form(default=1, description="处理优先级")
):
    """
    上传接口文档并立即开始后台处理
    
    返回会话ID，客户端可以使用此ID获取流式处理结果或查询状态
    """
    try:
        # 验证文件
        if not file.filename:
            raise HTTPException(status_code=400, detail="请选择要上传的文件")
        
        # 检查并发限制
        if len(document_handler.active_sessions) >= document_handler.max_concurrent_sessions:
            raise HTTPException(status_code=429, detail="服务器繁忙，请稍后重试")
        
        # 生成会话ID
        session_id = str(uuid.uuid4())
        
        # 保存上传的文件
        file_path = await document_handler.save_uploaded_file(file)
        
        # 创建处理请求
        request = DocumentUploadRequest(
            agent_type=agent_type,
            max_rounds=max_rounds,
            custom_prompt=custom_prompt,
            priority=priority
        )
        
        # 创建会话
        session = DocumentProcessSession(session_id, file_path, request)
        document_handler.active_sessions[session_id] = session
        
        # 创建并启动后台处理任务（使用asyncio.create_task以便后续可以取消）
        task = asyncio.create_task(start_document_processing_task(session_id))
        session.task = task
        document_handler.active_tasks[session_id] = task
        
        upload_msg = f"文档上传成功并启动后台处理，会话ID: {session_id}, 文件: {file.filename}"
        logger.info(upload_msg)
        
        return {
            "session_id": session_id,
            "status": "processing_started",
            "message": "文档上传成功，后台处理已开始",
            "filename": file.filename,
            "file_size": os.path.getsize(file_path),
            "timestamp": datetime.now().isoformat(),
            "status_url": f"/api/v1/document/session/{session_id}/status",
            "completion_url": f"/api/v1/document/session/{session_id}/completed"
        }
        
    except Exception as e:
        logger.error(f"文档上传失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.get("/api/v1/document/session/{session_id}/completed")
async def check_task_completion(session_id: str):
    """
    检查任务是否执行完成
    
    返回任务完成状态和相关信息
    """
    if session_id not in document_handler.active_sessions:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    
    session = document_handler.active_sessions[session_id]
    
    # 判断任务是否完成
    is_completed = session.status in [
        DocumentProcessStatus.COMPLETED,
        DocumentProcessStatus.ERROR,
        DocumentProcessStatus.CANCELLED
    ]
    
    # 构建响应数据
    response_data = {
        "session_id": session_id,
        "is_completed": is_completed,
        "status": session.status.value,
        "progress": session.progress,
        "start_time": session.start_time.isoformat(),
        "execution_time": (datetime.now() - session.start_time).total_seconds(),
        "agent_type": session.request.agent_type
    }
    
    # 如果任务完成，添加完成时间和最终状态
    if is_completed:
        response_data.update({
            "completed_at": datetime.now().isoformat(),
            "final_status": session.status.value,
            "error_message": session.error_message if session.status == DocumentProcessStatus.ERROR else None
        })
        
        # 如果有Agent信息，添加执行统计
        if session.agent:
            response_data.update({
                "agent_id": session.agent.agent_id,
                "agent_name": session.agent.agent_name,
                "total_rounds": session.agent.current_round,
                "max_rounds": getattr(session.agent, 'max_rounds', None),
                "token_usage": session.agent.get_token_usage_info() if hasattr(session.agent, 'get_token_usage_info') else None
            })
    
    # 如果任务正在进行，添加当前状态信息
    elif session.status == DocumentProcessStatus.PROCESSING and session.agent:
        response_data.update({
            "agent_id": session.agent.agent_id,
            "agent_name": session.agent.agent_name,
            "current_round": session.agent.current_round,
            "max_rounds": getattr(session.agent, 'max_rounds', None),
            "current_state": session.current_state,
            "current_tool": session.current_tool
        })
    
    return response_data


@app.get("/api/v1/document/sessions")
async def get_active_sessions():
    """获取活跃会话列表"""
    sessions = []
    for session_id, session in document_handler.active_sessions.items():
        session_info = {
            "session_id": session_id,
            "status": session.status.value,
            "progress": session.progress,
            "start_time": session.start_time.isoformat(),
            "agent_type": session.request.agent_type,
            "priority": session.request.priority,
            "current_round": session.agent.current_round if session.agent else 0,
            "error_message": session.error_message
        }
        
        if session.agent:
            session_info.update({
                "agent_id": session.agent.agent_id,
                "agent_name": session.agent.agent_name,
            })
        
        sessions.append(session_info)
    
    return {
        "active_sessions": sessions,
        "total_count": len(sessions),
        "max_concurrent": document_handler.max_concurrent_sessions,
        "available_slots": document_handler.max_concurrent_sessions - len(sessions)
    }


@app.get("/api/v1/document/session/{session_id}/status")
async def get_session_status(session_id: str):
    """获取特定会话的状态"""
    if session_id not in document_handler.active_sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = document_handler.active_sessions[session_id]
    
    status_info = {
        "session_id": session_id,
        "status": session.status.value,
        "progress": session.progress,
        "start_time": session.start_time.isoformat(),
        "agent_type": session.request.agent_type,
        "current_state": session.current_state,
        "current_tool": session.current_tool,
        "error_message": session.error_message,
        "execution_time": (datetime.now() - session.start_time).total_seconds()
    }
    
    if session.agent:
        status_info.update({
            "agent_id": session.agent.agent_id,
            "agent_name": session.agent.agent_name,
            "current_round": session.agent.current_round,
            "max_rounds": session.agent.max_rounds if hasattr(session.agent, 'max_rounds') else None
        })
    
    return status_info


@app.delete("/api/v1/document/session/{session_id}")
async def cancel_session(session_id: str):
    """取消会话处理"""
    if session_id not in document_handler.active_sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = document_handler.active_sessions[session_id]
    
    # 设置取消状态
    session.status = DocumentProcessStatus.CANCELLED
    
    # 记录取消操作
    if session.session_logger:
        session.session_logger.info(f"[{session_id}] 收到取消请求，正在停止任务...")
    logger.info(f"正在取消会话 {session_id} 的处理任务")
    
    # 取消后台任务
    task = None
    if session.task:
        task = session.task
    elif session_id in document_handler.active_tasks:
        task = document_handler.active_tasks[session_id]
    
    if task and not task.done():
        try:
            # 取消任务
            task.cancel()
            logger.info(f"已发送取消信号给会话 {session_id} 的任务")
            
            # 等待任务取消完成（最多等待5秒）
            try:
                await asyncio.wait_for(task, timeout=5.0)
                logger.info(f"会话 {session_id} 的任务已成功取消")
            except asyncio.TimeoutError:
                logger.warning(f"会话 {session_id} 的任务取消超时（5秒），任务可能仍在运行")
            except asyncio.CancelledError:
                # 任务已取消，这是正常的
                logger.info(f"会话 {session_id} 的任务已成功取消（CancelledError）")
            
            # 从活跃任务列表中移除
            if session_id in document_handler.active_tasks:
                del document_handler.active_tasks[session_id]
                
        except Exception as e:
            error_msg = f"取消任务时出错: {e}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            if session.session_logger:
                session.session_logger.error(f"[{session_id}] {error_msg}")
        finally:
            # 确保任务引用被清除
            if session:
                session.task = None
    
    # 尝试停止Agent（如果已创建）
    if session.agent:
        try:
            # 设置Agent状态为ERROR以停止执行
            if hasattr(session.agent, 'state'):
                from backend.agent.schema import AgentState
                session.agent.state = AgentState.ERROR
            if session.session_logger:
                session.session_logger.info(f"[{session_id}] Agent状态已设置为ERROR")
        except Exception as e:
            logger.warning(f"设置Agent状态失败: {e}")
    
    # 清理会话资源
    await document_handler.cleanup_session(session_id)
    
    if session.session_logger:
        session.session_logger.info(f"[{session_id}] 会话已完全取消并清理")
    
    return {
        "status": "success",
        "message": "会话已取消",
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/v1/document/session/{session_id}/files")
async def get_session_files(session_id: str):
    """
    获取指定session下的所有文件列表
    
    返回文件列表，包括文件名、路径、大小等信息
    注意：此接口不依赖document_handler，直接从文件系统读取
    """
    # 直接从文件系统获取工作目录（不依赖document_handler）
    from backend.agent.base import DEFAULT_WORKDIR
    work_dir = os.path.join(DEFAULT_WORKDIR, session_id)
    
    if not os.path.exists(work_dir):
        return {
            "session_id": session_id,
            "work_dir": work_dir,
            "files": [],
            "total_count": 0,
            "message": "工作目录不存在"
        }
    
    # 递归获取所有文件
    files_list = []
    try:
        for root, dirs, files in os.walk(work_dir):
            # 计算相对路径
            rel_root = os.path.relpath(root, work_dir)
            if rel_root == '.':
                rel_root = ''
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.join(rel_root, file) if rel_root else file
                
                try:
                    file_stat = os.stat(file_path)
                    files_list.append({
                        "filename": file,
                        "relative_path": rel_path.replace('\\', '/'),  # 统一使用正斜杠
                        "absolute_path": file_path,
                        "size": file_stat.st_size,
                        "modified_time": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                        "is_file": True
                    })
                except Exception as e:
                    logger.warning(f"无法获取文件信息 {file_path}: {e}")
    except Exception as e:
        logger.error(f"遍历文件失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")
    
    return {
        "session_id": session_id,
        "work_dir": work_dir,
        "files": files_list,
        "total_count": len(files_list),
        "total_size": sum(f["size"] for f in files_list)
    }


@app.get("/api/v1/document/session/{session_id}/files/download")
async def download_session_file(session_id: str, file_path: str):
    """
    下载指定session下的文件
    
    参数:
    - session_id: 会话ID
    - file_path: 文件的相对路径（相对于工作目录）
    注意：此接口不依赖document_handler，直接从文件系统读取
    """
    # 直接从文件系统获取工作目录（不依赖document_handler）
    from backend.agent.base import DEFAULT_WORKDIR
    work_dir = os.path.join(DEFAULT_WORKDIR, session_id)
    
    # 构建完整文件路径
    # 防止路径遍历攻击
    if '..' in file_path or file_path.startswith('/'):
        raise HTTPException(status_code=400, detail="非法的文件路径")
    
    full_path = os.path.normpath(os.path.join(work_dir, file_path))
    
    # 确保文件在工作目录内
    if not full_path.startswith(os.path.normpath(work_dir)):
        raise HTTPException(status_code=400, detail="文件路径超出工作目录范围")
    
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=full_path,
        filename=os.path.basename(full_path),
        media_type='application/octet-stream'
    )


def validate_session_id(session_id: str) -> bool:
    """
    验证session_id是否为有效的UUID格式
    
    参数:
    - session_id: 要验证的session ID
    
    返回:
    - True: 如果是有效的UUID格式
    - False: 如果不是有效的UUID格式
    """
    try:
        # 尝试解析为UUID，如果成功则为有效格式
        uuid.UUID(session_id)
        return True
    except (ValueError, TypeError):
        return False


@app.delete("/api/v1/document/session/{session_id}/files")
async def delete_session_files(session_id: str):
    """
    删除指定session的整个工作目录文件夹
    
    注意：此操作不可恢复，请谨慎使用
    注意：此接口不依赖document_handler，直接从文件系统操作
    注意：只允许删除符合UUID格式的session_id目录，防止误删除其他文件夹
    """
    # 验证session_id格式，必须是有效的UUID格式
    if not validate_session_id(session_id):
        raise HTTPException(
            status_code=400, 
            detail=f"非法的session_id格式。session_id必须是有效的UUID格式，当前值: {session_id}"
        )
    
    # 直接从文件系统获取工作目录（不依赖document_handler）
    from backend.agent.base import DEFAULT_WORKDIR
    work_dir = os.path.join(DEFAULT_WORKDIR, session_id)
    
    # 验证路径安全性：确保工作目录确实在DEFAULT_WORKDIR下，并且目录名就是session_id
    # 防止路径遍历攻击
    work_dir = os.path.normpath(work_dir)
    default_workdir = os.path.normpath(DEFAULT_WORKDIR)
    
    # 确保不会删除DEFAULT_WORKDIR本身
    if work_dir == default_workdir:
        raise HTTPException(status_code=400, detail="禁止删除项目根目录")
    
    # 确保工作目录确实在DEFAULT_WORKDIR下
    if not work_dir.startswith(default_workdir):
        raise HTTPException(status_code=400, detail="非法的路径，安全验证失败")
    
    # 确保目录名就是session_id，防止类似 "../../backend" 这样的路径
    if os.path.basename(work_dir) != session_id:
        raise HTTPException(status_code=400, detail="路径验证失败，目录名必须与session_id一致")
    
    # 确保work_dir是DEFAULT_WORKDIR的直接子目录（防止跨级删除）
    # 例如：DEFAULT_WORKDIR/session_id 是正确的
    # 但 DEFAULT_WORKDIR/../backend 是不允许的
    parent_dir = os.path.dirname(work_dir)
    if parent_dir != default_workdir:
        raise HTTPException(status_code=400, detail="只能删除DEFAULT_WORKDIR的直接子目录")
    
    # 额外安全验证：确保不会删除项目根目录或系统重要目录
    # 虽然UUID格式已经基本防止了这个问题，但这是额外的保护
    forbidden_names = {'backend', 'frontend', 'config', 'logs', 'data', 'scripts', 'tests', 'utils'}
    if session_id.lower() in forbidden_names:
        raise HTTPException(status_code=400, detail=f"禁止删除系统目录: {session_id}")
    
    if not os.path.exists(work_dir):
        return {
            "status": "success",
            "message": "工作目录不存在，无需删除",
            "session_id": session_id,
            "work_dir": work_dir
        }
    
    # 验证确实是目录而不是文件
    if not os.path.isdir(work_dir):
        raise HTTPException(status_code=400, detail="指定路径不是目录")
    
    deleted_files = []
    deleted_count = 0
    total_size = 0
    
    try:
        # 先统计要删除的文件（用于日志记录）
        for root, dirs, files in os.walk(work_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path)
                    deleted_files.append(file_path)
                    deleted_count += 1
                    total_size += file_size
                except Exception as e:
                    logger.warning(f"统计文件信息失败 {file_path}: {e}")
        
        # 删除整个工作目录（包括目录本身）
        shutil.rmtree(work_dir)
        
        # 记录删除操作
        logger.info(f"会话 {session_id} 的整个工作目录已删除，共删除了 {deleted_count} 个文件，总大小: {total_size} bytes")
        
        return {
            "status": "success",
            "message": f"成功删除整个session目录，共 {deleted_count} 个文件",
            "session_id": session_id,
            "work_dir": work_dir,
            "deleted_count": deleted_count,
            "deleted_size": total_size,
            "deleted_files": deleted_files[:10] if len(deleted_files) > 10 else deleted_files,  # 只返回前10个文件路径
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        error_msg = f"删除目录失败: {e}"
        tb = traceback.format_exc()
        logger.error(f"[{session_id}] {error_msg}\n{tb}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/v1/document/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(document_handler.active_sessions),
        "max_concurrent": document_handler.max_concurrent_sessions,
        "available_slots": document_handler.max_concurrent_sessions - len(document_handler.active_sessions)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=12389)
