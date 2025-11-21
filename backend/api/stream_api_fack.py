"""
流式API假实现：接口签名与 `stream_api.py` 一致，但返回预置的测试数据。
"""

import sys
from pathlib import Path
import json
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator
from enum import Enum
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger

# 项目根目录
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 日志配置与正式版保持一致
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    logs_dir / "stream_api_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="INFO",
    encoding="utf-8"
)


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: MessageRole
    content: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentEventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_CONTENT = "agent_content"
    TOOL_CALL_START = "tool_call_start"
    TOOL_ARGS = "tool_args"
    TOOL_RESULT_START = "tool_result_start"
    TOOL_RESULT_CONTENT = "tool_result_content"
    TOOL_RESULT_END = "tool_result_end"
    AGENT_RUNNING = "agent_running"
    AGENT_FINISHED = "agent_finished"
    USER_QUESTION = "ask_user"
    ERROR = "error"


class ToolInfo(BaseModel):
    name: Optional[str] = None
    call_id: Optional[str] = None


class AgentStreamPayload(BaseModel):
    event_type: AgentEventType
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    current_round: Optional[int] = None

    tool: Optional[ToolInfo] = None
    tool_args: Optional[Dict[str, Any]] = None

    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    def to_json(self) -> str:
        return self.model_dump_json(ensure_ascii=False)


class AgentExecuteRequest(BaseModel):
    query: str = Field(..., description="用户查询")
    agent_type: str = Field(default="PlanAgent", description="Agent类型")
    llm_config: Optional[Dict[str, Any]] = Field(default=None, description="LLM配置")
    max_rounds: Optional[int] = Field(default=80, description="最大执行轮数")
    stream_file_operations: bool = Field(default=True, description="是否启用流式文件操作")
    session_id: Optional[str] = Field(default=None, description="复用会话ID（如为空则新建会话）")


class UserAnswerRequest(BaseModel):
    session_id: str = Field(..., description="会话ID")
    interaction_id: str = Field(..., description="交互ID")
    answer: str = Field(..., description="用户回答")
    answer_type: str = Field(default="text", description="回答类型：text/choice/confirm")


class StreamAPIHandler:
    """流式API处理器（假实现：输出测试数据文件内容）"""

    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.test_data_path = project_root / "test_data.json"

    async def execute_agent_stream(self, request: AgentExecuteRequest) -> AsyncGenerator[str, None]:
        session_id = request.session_id or str(uuid.uuid4())

        logger.info(f"[假会话] session_id={session_id}, agent_type={request.agent_type}, query={request.query[:100]}")

        if not self.test_data_path.exists():
            error_message = f"测试数据文件不存在: {self.test_data_path}"
            logger.error(f"[假流式执行] {error_message}")
            error_event = AgentStreamPayload(
                event_type=AgentEventType.ERROR,
                agent_id="fake_agent",
                agent_name="FakeStreamAgent",
                session_id=session_id,
                error_message=error_message,
                data={"path": str(self.test_data_path)}
            )
            yield f"data: {error_event.to_json()}\n\n"
            return

        try:
            with self.test_data_path.open("r", encoding="utf-8") as file_obj:
                async for chunk in self._yield_test_lines(file_obj, session_id):
                    yield chunk
            logger.info(f"[假流式执行] 推送完成 session_id={session_id}")
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(f"[假流式执行] 读取测试数据失败: {exc}")
            logger.error(f"[假流式执行] Traceback:\n{tb}")
            error_event = AgentStreamPayload(
                event_type=AgentEventType.ERROR,
                agent_id="fake_agent",
                agent_name="FakeStreamAgent",
                session_id=session_id,
                error_message=str(exc),
                data={"traceback": tb}
            )
            yield f"data: {error_event.to_json()}\n\n"

    async def _yield_test_lines(self, file_obj, session_id: str, delay: float = 0.05) -> AsyncGenerator[str, None]:
        """逐行推送测试数据，封装成 SSE 格式"""
        for raw_line in file_obj:
            line = raw_line.strip()
            if not line:
                continue
            yield f"data: {line}\n\n"
            await asyncio.sleep(delay)

        completion_event = AgentStreamPayload(
            event_type=AgentEventType.AGENT_CONTENT,
            agent_id="fake_agent",
            agent_name="FakeStreamAgent",
            session_id=session_id,
            content="测试数据推送完成"
        )
        yield f"data: {completion_event.to_json()}\n\n"


app = FastAPI(title="Agent流式执行API - Fake", version="1.0.0")
stream_handler = StreamAPIHandler()

# 与正式接口一致的 CORS 配置
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
    generator = stream_handler.execute_agent_stream(request)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.post("/api/v1/agent/answer")
async def api_agent_answer(_: UserAnswerRequest):
    """假实现暂不支持用户回答，直接抛出异常以保持行为一致。"""
    raise HTTPException(status_code=400, detail="Fake stream API 不支持用户交互")


@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(), "fake": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
一个独立的假流式接口示例：读取 `test_data.json` 并通过 SSE 推送。
"""

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator
import traceback

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from loguru import logger

# 项目根目录
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.agent.general_agent.base import AgentStreamPayload, AgentEventType
from backend.api.stream_api import AgentExecuteRequest


app = FastAPI(title="Fake Stream API", version="1.0.0")
test_data_path = project_root / "test_data.json"


async def fake_stream(delay: float = 0.05) -> AsyncGenerator[str, None]:
    """读取 `test_data.json`，逐行以 SSE 形式输出。"""
    if not test_data_path.exists():
        error_message = f"测试数据文件不存在: {test_data_path}"
        logger.error(f"[FakeStream] {error_message}")
        error_event = AgentStreamPayload(
            event_type=AgentEventType.ERROR,
            agent_id=None,
            agent_name="FakeStream",
            session_id=None,
            current_round=None,
            error_message=error_message,
            data={"path": str(test_data_path)}
        )
        yield f"data: {error_event.to_json()}\n\n"
        return

    logger.info(f"[FakeStream] 使用测试数据: {test_data_path}")
    try:
        with test_data_path.open("r", encoding="utf-8") as file_obj:
            for raw_line in file_obj:
                line = raw_line.strip()
                if not line:
                    continue
                yield f"data: {line}\n\n"
                await asyncio.sleep(delay)

        completion_event = AgentStreamPayload(
            event_type=AgentEventType.AGENT_CONTENT,
            agent_id="fake_stream",
            agent_name="FakeStream",
            session_id=None,
            current_round=None,
            content="测试数据推送完成"
        )
        yield f"data: {completion_event.to_json()}\n\n"
        logger.info("[FakeStream] 推送完成")
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error(f"[FakeStream] 读取测试数据失败: {exc}")
        logger.error(f"[FakeStream] Traceback:\n{tb}")
        error_event = AgentStreamPayload(
            event_type=AgentEventType.ERROR,
            agent_id=None,
            agent_name="FakeStream",
            session_id=None,
            current_round=None,
            error_message=str(exc),
            data={"traceback": tb}
        )
        yield f"data: {error_event.to_json()}\n\n"


@app.post("/api/v1/agent/stream")
async def fake_stream_endpoint(request: AgentExecuteRequest):
    """基于测试数据的假流式接口，入参与正式接口保持一致。"""
    logger.info(f"[FakeStream] 接收到请求，agent_type={request.agent_type}, query={request.query[:50]}{'...' if len(request.query) > 50 else ''}")
    generator = fake_stream(delay=0.05)
    return StreamingResponse(generator, media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

