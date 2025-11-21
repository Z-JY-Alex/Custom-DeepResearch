"""
Agent基类模块：提供agent创建、prompt管理、工具使用和执行控制功能
"""

from datetime import datetime
import json
import os
from pathlib import Path
import uuid
import inspect
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from enum import Enum
from loguru import logger
import traceback

from pydantic import BaseModel, Field

# 导入相关模块
from backend.memory.base import BaseMemory
from backend.agent.schema import AgentState
from backend.prompts.base import BasePrompt
from backend.tools.base import BaseTool, ToolFunction, ToolCallResult
from backend.llm.base import BaseLLM, Message, MessageRole, LLMConfig
from backend.llm.llm import OpenAILLM
from backend.mcp_client import MCPClient
from backend.artifacts.manager import ArtifactManager
from backend.tools.file_operations import FileCreateTool, FileReadTool
from backend.tools.stream_file_operations import StreamFileOperationTool
from backend.tools.artifact_write import ArtifactWriteTool
from backend.tools.terminate import Terminate
from backend.llm.token_counter import TokenCounter
from backend.tools.user_interaction import UserInteractionTool

CURRUENT_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# 获取项目根目录（从当前文件向上三级：backend/agent/ -> backend/ -> project root）
DEFAULT_WORKDIR = str(Path(__file__).parent.parent.parent.parent.absolute())

class AgentEventType(str, Enum):
    """Agent流事件类型（统一前后端约定）"""
    AGENT_START = "agent_start"
    AGENT_CONTENT = "agent_content"
    TOOL_CALL_START = "tool_call_start"
    TOOL_ARGS = "tool_args"
    TOOL_RESULT_START = "tool_result_start"
    TOOL_RESULT_CONTENT = "tool_result_content"
    TOOL_RESULT_END = "tool_result_end"
    AGENT_RUNNING = "agent_running"
    AGENT_FINISHED = "agent_finished"
    USER_QUESTION = "ask_user"  # 与前端保持一致
    ERROR = "error"


class ToolInfo(BaseModel):
    """工具信息"""
    name: Optional[str] = Field(default=None, description="工具名称")
    call_id: Optional[str] = Field(default=None, description="工具调用ID")


class AgentStreamPayload(BaseModel):
    """统一的Agent流式事件负载结构，便于前端解析"""
    event_type: AgentEventType = Field(..., description="事件类型")
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="事件ID")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="时间戳")

    # Agent信息
    agent_id: Optional[str] = Field(default=None, description="Agent ID")
    agent_name: Optional[str] = Field(default=None, description="Agent名称")
    session_id: Optional[str] = Field(default=None, description="会话ID")
    current_round: Optional[int] = Field(default=None, description="当前执行轮次")

    # 工具信息
    tool: Optional[ToolInfo] = Field(default=None, description="工具信息")
    tool_args: Optional[Dict[str, Any]] = Field(default=None, description="工具参数")

    # 内容与扩展数据
    content: Optional[str] = Field(default=None, description="文本内容")
    data: Optional[Dict[str, Any]] = Field(default=None, description="结构化扩展数据")
    error_message: Optional[str] = Field(default=None, description="错误消息")

    class Config:
        arbitrary_types_allowed = True

    def to_json(self) -> str:
        return self.model_dump_json(ensure_ascii=False)

class BaseAgent(BaseModel, ABC):
    """Agent基类"""
    
    # 基本属性
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Agent ID")
    agent_name: str = Field(..., description="Agent名称")
    agent_description: str = Field(..., description="Agent描述")
    
    # 状态管理
    state: AgentState = Field(default=AgentState.IDLE, description="Agent状态")
    
    # session_id和工作目录
    session_id: Optional[str] = Field(default=None, description="会话ID")
    work_dir: Optional[str] = Field(default=DEFAULT_WORKDIR, description="工作目录")
    current_time: Optional[str] = Field(default=CURRUENT_TIME, description="当前时间")

    # Prompt管理
    base_prompt: Optional[BasePrompt] = Field(default=None, description="基础prompt")
    instruction: Optional[str] = Field(default=None, description="用户自定义prompt, 代替base_prompt")
    
    # 工具管理
    tools: List[BaseTool] = Field(default_factory=list, description="可用工具列表")
    mcp_config: Optional[dict] = Field(default=None, description="MCP配置")
    
    # LLM配置
    llm: Optional[BaseLLM] = Field(default=None, description="语言模型实例")
    llm_config: Optional[LLMConfig] = Field(default=None, description="LLM配置")
    
    # 记忆模块
    memory: BaseMemory = Field(default_factory=BaseMemory, description="记忆模块")
    artifact_manager: Optional[ArtifactManager] = Field(default=None, description="Artifact管理器")
    
    # 通用工具
    file_operation_tool: Optional[StreamFileOperationTool] = Field(default=None, description="流式文件保存、修改工具")
    file_read_tool: Optional[FileReadTool] = Field(default=None, description="文件读取工具")
    artifact_tool: Optional[ArtifactWriteTool] = Field(default=None, description="Artifact写入工具")
    terminate: Optional[Terminate] = Field(default=None, description="终止工具实例")

    # 用户交互
    user_interaction_tool: Optional[UserInteractionTool] = Field(default=None, description="用户交互工具")
    
    # Token计算
    token_counter: TokenCounter = TokenCounter("gpt-4o")

    # Token管理配置
    max_context_tokens: int = Field(default=200000, description="最大上下文Token数")
    compression_threshold: float = Field(default=0.8, description="触发压缩的Token使用率阈值")
    preserve_recent_rounds: int = Field(default=5, description="保留最近N轮对话不压缩")
    preserve_initial_rounds: int = Field(default=3, description="保留开始N轮对话不压缩")
    current_token_count: int = Field(default=0, description="当前Token使用量")

    # 执行配置
    max_rounds: int = Field(default=80, description="最大执行次数，避免死循环")
    current_round: int = Field(default=0, description="当前执行轮数")
    default_timeout: float = Field(default=300.0, description="默认超时时间")
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, session_id: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        # 初始化LLM
        if self.llm is None and self.llm_config:
            self.llm = OpenAILLM(self.llm_config)

        self.session_id = session_id

        if self.session_id:
            self.work_dir = os.path.join(DEFAULT_WORKDIR, self.session_id)
            os.makedirs(self.work_dir, exist_ok=True)
            logger.info(f"为会话 {self.session_id} 创建工作目录: {self.work_dir}")
        else:
            self.work_dir = DEFAULT_WORKDIR
        
        # self.file_create_tool = FileCreateTool()
        self.file_operation_tool = StreamFileOperationTool()
        self.file_read_tool = FileReadTool()
        self.artifact_tool = ArtifactWriteTool(artifact_manager=self.artifact_manager)
        self.terminate = Terminate()

        # self.add_tool(self.file_create_tool)
        self.add_tool(self.file_operation_tool)
        self.add_tool(self.file_read_tool)
        self.add_tool(self.artifact_tool)
        self.add_tool(self.terminate)

        self.user_interaction_tool = UserInteractionTool()
        self.add_tool(self.user_interaction_tool)
        
    def get_prompt(
        self,
        role: str = "智能助手",
        user_profile: Optional[Dict[str, Any]] = None,
        plan_info: Optional[str] = None,
        current_task_description: Optional[str] = None,
        current_task_objectives: Optional[List[str]] = None,
        context_info: Optional[Dict[str, Any]] = None,
        output_format: Optional[str] = None,
    ) -> str:
        """创建prompt"""
        if self.instruction:
            self.prompt = self.instruction
            return self.prompt
        prompt = BasePrompt(
            role=role,
            user_profile=user_profile,
            plan_info=plan_info,
            current_task_description=current_task_description,
            current_task_objectives=current_task_objectives,
            context_info=context_info or {},
            output_format=output_format
        )
        self.prompt = prompt.generate_prompt()
        return self.prompt
    
    
    def add_tool(self, tool: Union[BaseTool, ToolFunction]) -> None:
        """添加工具"""
        if tool not in self.tools:
            self.tools.append(tool)
            logger.info(f"Agent {self.agent_name} 添加工具: {tool.name}")
    
    
    def remove_tool(self, tool_name: str) -> bool:
        """移除工具"""
        for i, tool in enumerate(self.tools):
            if tool.name == tool_name:
                self.tools.pop(i)
                logger.info(f"Agent {self.name} 移除工具: {tool_name}")
                return True
        return False
    
    def get_tool_by_name(self, tool_name: str) -> Optional[Union[BaseTool, ToolFunction]]:
        """根据名称获取工具"""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return [tool.name for tool in self.tools]

    def calculate_current_tokens(self) -> int:
        """计算当前对话历史的总Token数"""
        current_tokens = self.memory.calculate_agent_tokens(self.agent_id)
        self.current_token_count = current_tokens
        return current_tokens

    def should_compress_memory(self) -> bool:
        """判断是否需要压缩内存"""
        return self.memory.should_compress_agent_memory(
            agent_id=self.agent_id,
            max_context_tokens=self.max_context_tokens,
            compression_threshold=self.compression_threshold
        )

    async def compress_conversation_history(self) -> bool:
        """智能压缩对话历史"""
        return await self.memory.compress_agent_conversation_history(
            agent_id=self.agent_id,
            preserve_initial_rounds=self.preserve_initial_rounds,
            preserve_recent_rounds=self.preserve_recent_rounds
        )

    def get_token_usage_info(self) -> Dict[str, Any]:
        """获取Token使用情况信息"""
        # 从memory获取基础信息
        memory_info = self.memory.get_agent_memory_info(self.agent_id)
        current_tokens = memory_info["token_count"]
        usage_ratio = current_tokens / self.max_context_tokens if self.max_context_tokens > 0 else 0

        # 结合Agent配置信息
        return {
            **memory_info,
            "agent_name": self.agent_name,
            "max_tokens": self.max_context_tokens,
            "usage_ratio": usage_ratio,
            "compression_threshold": self.compression_threshold,
            "needs_compression": self.should_compress_memory(),
            "preserve_initial": self.preserve_initial_rounds,
            "preserve_recent": self.preserve_recent_rounds,
            "compression_enabled": True
        }

    def reset_token_count(self) -> None:
        """重置Token计数"""
        self.current_token_count = 0
        success = self.memory.reset_agent_memory(self.agent_id)
        if success:
            logger.info(f"Agent {self.agent_name} Token计数和内存已重置")
        else:
            logger.warning(f"Agent {self.agent_name} 内存重置失败")

    def update_compression_settings(
        self,
        max_context_tokens: Optional[int] = None,
        compression_threshold: Optional[float] = None,
        preserve_recent_rounds: Optional[int] = None,
        preserve_initial_rounds: Optional[int] = None
    ) -> None:
        """更新压缩设置"""
        if max_context_tokens is not None:
            self.max_context_tokens = max_context_tokens
        if compression_threshold is not None:
            self.compression_threshold = max(0.1, min(1.0, compression_threshold))
        if preserve_recent_rounds is not None:
            self.preserve_recent_rounds = max(1, preserve_recent_rounds)
        if preserve_initial_rounds is not None:
            self.preserve_initial_rounds = max(1, preserve_initial_rounds)

        logger.info(f"Agent {self.agent_name} 压缩设置已更新: "
                   f"最大Token={self.max_context_tokens}, "
                   f"压缩阈值={self.compression_threshold}, "
                   f"保留最近={self.preserve_recent_rounds}轮, "
                   f"保留开始={self.preserve_initial_rounds}轮")
    
    
    async def execute_tools(self, tool_calls):
        """执行工具调用，根据工具的parallel属性决定是否并行执行"""
        logger.info(f"准备执行 {len(tool_calls)} 个工具调用")
        
        # 更新消息历史
        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_calls=tool_calls,
                metadata={"current_round": self.current_round}
            )
        ]

        # 先遍历所有工具，检查parallel属性并分组
        parallel_tools = []  # 支持并行的工具列表（索引，tool_call, tool_instance, arguments）
        sequential_tools = []  # 需要顺序执行的工具列表
        
        for i, tool_call in enumerate(tool_calls):
            function_name = tool_call.function['name']
            arguments = json.loads(tool_call.function['arguments'])
            
            # 特殊处理 terminate 和 ask_user，必须立即执行
            if function_name in ("terminate", "ask_user"):
                async for chunk in self._execute_single_tool(i, tool_call, messages):
                    yield chunk
                
                self.memory.states[self.agent_id]["all_history"].extend(messages)
                self.state = AgentState.FINISHED
                return
            
            tool_instance = self.get_tool_by_name(function_name)
            if not tool_instance:
                # 工具不存在，放在顺序执行列表中处理错误
                sequential_tools.append((i, tool_call, None, arguments))
                continue
            
            # 检查工具的parallel属性（从工具实例或工具定义中获取）
            is_parallel = getattr(tool_instance, 'parallel', False)
            
            if is_parallel:
                parallel_tools.append((i, tool_call, tool_instance, arguments))
            else:
                sequential_tools.append((i, tool_call, tool_instance, arguments))
        
        # 先并行执行所有支持并行的工具
        if parallel_tools:
            async for chunk in self._execute_tools_parallel(parallel_tools, messages):
                yield chunk
        
        # 然后顺序执行不支持并行的工具
        for i, tool_call, tool_instance, arguments in sequential_tools:
            async for chunk in self._execute_single_tool(i, tool_call, messages, tool_instance, arguments):
                yield chunk
        
        self.memory.states[self.agent_id]["all_history"].extend(messages)

    async def _execute_tools_parallel(self, parallel_tools, messages):
        """并发执行一组工具，然后按顺序流式输出结果，保持与顺序执行完全一致的输出格式"""
        
        # 创建并发任务：收集所有工具的完整执行流程
        async def collect_tool_execution(tool_idx, tool_call, tool_instance, tool_args):
            """收集单个工具的完整执行流程，包括所有事件和流式输出"""
            function_name = tool_call.function['name']
            execution_events = []
            
            try:
                # 1. 工具调用开始事件
                execution_events.append(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_CALL_START,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                ).to_json())
                
                # 2. 工具参数事件
                execution_events.append(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_ARGS,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                    tool_args=tool_args,
                ).to_json())
                
                if not tool_instance:
                    # 工具不存在的错误处理
                    error_msg = f"未找到工具: {function_name}"
                    execution_events.append(AgentStreamPayload(
                        event_type=AgentEventType.ERROR,
                        agent_id=self.agent_id,
                        agent_name=self.agent_name,
                        session_id=self.session_id,
                        current_round=self.current_round,
                        tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                        error_message=error_msg,
                    ).to_json())
                    return tool_idx, tool_call, execution_events, None, (error_msg, None)
                
                # 3. 工具结果开始事件
                execution_events.append(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_RESULT_START,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                ).to_json())
                
                # 4. 收集工具执行的流式输出
                cur_tool_res_user = ""  # 用户看的结果
                cur_tool_res_internal = ""  # 内部完整结果
                tool_result_obj = None  # 保存 ToolCallResult 对象

                async for chunk in self._tool_reponse(tool_instance(**tool_args)):
                    # 如果 chunk 是 ToolCallResult 对象
                    if isinstance(chunk, ToolCallResult):
                        tool_result_obj = chunk
                        user_output = chunk.get_user_output() if hasattr(chunk, 'get_user_output') else str(chunk)
                        internal_output = chunk.get_internal_output() if hasattr(chunk, 'get_internal_output') else str(chunk)

                        cur_tool_res_user += user_output
                        cur_tool_res_internal += internal_output

                        # 流式输出用户友好的结果
                        execution_events.append(AgentStreamPayload(
                            event_type=AgentEventType.TOOL_RESULT_CONTENT,
                            agent_id=self.agent_id,
                            agent_name=self.agent_name,
                            session_id=self.session_id,
                            current_round=self.current_round,
                            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                            content=user_output,
                        ).to_json())
                    # 如果 chunk 已经是 AgentStreamPayload 格式，直接保存
                    elif self._is_agent_stream_payload(chunk):
                        execution_events.append(chunk)
                        # 为了记录到消息历史，需要提取内容
                        try:
                            chunk_data = json.loads(chunk.strip())
                            if isinstance(chunk_data, dict) and "content" in chunk_data:
                                content_str = str(chunk_data.get("content", ""))
                                cur_tool_res_user += content_str
                                cur_tool_res_internal += content_str
                        except (json.JSONDecodeError, AttributeError):
                            pass
                    else:
                        # 普通内容，包装成 AgentStreamPayload
                        chunk_str = str(chunk)
                        cur_tool_res_user += chunk_str
                        cur_tool_res_internal += chunk_str
                        execution_events.append(AgentStreamPayload(
                            event_type=AgentEventType.TOOL_RESULT_CONTENT,
                            agent_id=self.agent_id,
                            agent_name=self.agent_name,
                            session_id=self.session_id,
                            current_round=self.current_round,
                            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                            content=chunk_str,
                        ).to_json())
                
                # 5. 工具结果结束事件
                execution_events.append(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_RESULT_END,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                ).to_json())

                # 返回：索引、工具调用、执行事件列表、内部结果（用于保存）、错误信息
                return tool_idx, tool_call, execution_events, cur_tool_res_internal, None
                
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"{function_name} 执行失败: {str(e)}\n{tb}")
                
                # 添加错误事件
                execution_events.append(AgentStreamPayload(
                    event_type=AgentEventType.ERROR,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                    error_message=str(e),
                    data={"traceback": tb} if tb else {},
                ).to_json())
                
                return tool_idx, tool_call, execution_events, None, (str(e), tb)
        
        # 并发执行所有工具，收集完整的执行流程
        tasks = [collect_tool_execution(i, tool_call, tool_instance, arguments) 
                 for i, tool_call, tool_instance, arguments in parallel_tools]
        results = await asyncio.gather(*tasks)
        
        # 按原始顺序流式输出每个工具的完整执行流程
        for tool_idx, tool_call, execution_events, result_content, error_info in sorted(results, key=lambda x: x[0]):
            # 逐个输出该工具的所有事件，保持完整的执行流程
            for event in execution_events:
                yield event
            
            # 将结果添加到消息历史
            if error_info:
                error_msg, tb = error_info
                messages.append(
                    Message(
                        role=MessageRole.TOOL, content=f"工具执行失败: {error_msg}",
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tool_call_id=tool_call.id,
                        metadata={"current_round": self.current_round}
                    )
                )
            else:
                messages.append(
                    Message(
                        role=MessageRole.TOOL, content=result_content or "",
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tool_call_id=tool_call.id,
                        metadata={"current_round": self.current_round}
                    )
                )

    async def _execute_single_tool(self, tool_idx, tool_call, messages, tool_instance=None, arguments=None):
        """执行单个工具（顺序执行）"""
        function_name = tool_call.function['name']
        
        if arguments is None:
            arguments = json.loads(tool_call.function['arguments'])
        
        logger.info(f"执行工具: {function_name}")
        
        yield AgentStreamPayload(
            event_type=AgentEventType.TOOL_CALL_START,
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            session_id=self.session_id,
            current_round=self.current_round,
            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
        ).to_json()

        yield AgentStreamPayload(
            event_type=AgentEventType.TOOL_ARGS,
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            session_id=self.session_id,
            current_round=self.current_round,
            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
            tool_args=arguments,
        ).to_json()

        if tool_instance is None:
            tool_instance = self.get_tool_by_name(function_name)

        if not tool_instance:
            error_msg = f"未找到工具: {function_name}"
            logger.error(error_msg)
            yield AgentStreamPayload(
                event_type=AgentEventType.ERROR,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                error_message=error_msg,
            ).to_json()
            return

        try:
            cur_tool_res_user = ""  # 用户看的结果
            cur_tool_res_internal = ""  # 内部完整结果
            yield AgentStreamPayload(
                event_type=AgentEventType.TOOL_RESULT_START,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
            ).to_json()

            async for chunk in self._tool_reponse(tool_instance(**arguments)):
                # 如果 chunk 是 ToolCallResult 对象
                if isinstance(chunk, ToolCallResult):
                    user_output = chunk.get_user_output() if hasattr(chunk, 'get_user_output') else str(chunk)
                    internal_output = chunk.get_internal_output() if hasattr(chunk, 'get_internal_output') else str(chunk)

                    cur_tool_res_user += user_output
                    cur_tool_res_internal += internal_output

                    # 流式输出用户友好的结果
                    yield AgentStreamPayload(
                        event_type=AgentEventType.TOOL_RESULT_CONTENT,
                        agent_id=self.agent_id,
                        agent_name=self.agent_name,
                        session_id=self.session_id,
                        current_round=self.current_round,
                        tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                        content=user_output,
                    ).to_json()
                # 如果 chunk 已经是 AgentStreamPayload 格式，直接透传，避免嵌套
                elif self._is_agent_stream_payload(chunk):
                    yield chunk
                    # 为了记录到消息历史，需要提取内容
                    try:
                        chunk_data = json.loads(chunk.strip())
                        if isinstance(chunk_data, dict) and "content" in chunk_data:
                            content_str = str(chunk_data.get("content", ""))
                            cur_tool_res_user += content_str
                            cur_tool_res_internal += content_str
                    except (json.JSONDecodeError, AttributeError):
                        pass
                else:
                    chunk_str = str(chunk)
                    cur_tool_res_user += chunk_str
                    cur_tool_res_internal += chunk_str
                    yield AgentStreamPayload(
                        event_type=AgentEventType.TOOL_RESULT_CONTENT,
                        agent_id=self.agent_id,
                        agent_name=self.agent_name,
                        session_id=self.session_id,
                        current_round=self.current_round,
                        tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                        content=chunk_str,
                    ).to_json()

            yield AgentStreamPayload(
                event_type=AgentEventType.TOOL_RESULT_END,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
            ).to_json()

            if function_name == "terminate":
                self.state = AgentState.FINISHED
                messages.append(
                    Message(
                        role=MessageRole.TOOL, content=cur_tool_res_internal,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tool_call_id=tool_call.id,
                        metadata={"current_round": self.current_round}
                    )
                )
                return

            if function_name == "ask_user":
                self.state = AgentState.FINISHED
                messages.append(
                    Message(
                        role=MessageRole.TOOL, content=cur_tool_res_internal,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tool_call_id=tool_call.id,
                        metadata={"current_round": self.current_round}
                    )
                )
                return

        except Exception as e:
            cur_tool_res_internal = f"工具执行失败: {str(e)}"
            tb = traceback.format_exc()
            logger.error(f"{function_name} 执行失败: {e}\n{tb}")
            yield AgentStreamPayload(
                event_type=AgentEventType.ERROR,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                error_message=cur_tool_res_internal,
                data={"traceback": tb},
            ).to_json()

        messages.append(
            Message(
                role=MessageRole.TOOL, content=cur_tool_res_internal,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_call_id=tool_call.id,
                metadata={"current_round": self.current_round}
            )
        )


    def _is_agent_stream_payload(self, chunk: Any) -> bool:
        """
        判断 chunk 是否已经是 AgentStreamPayload 格式的 JSON 字符串
        避免重复包装导致嵌套
        """
        if not isinstance(chunk, str):
            return False
        try:
            chunk_clean = chunk.strip()
            if not chunk_clean.startswith('{'):
                return False
            data = json.loads(chunk_clean)
            # 检查是否包含 AgentStreamPayload 的特征字段
            if isinstance(data, dict) and "event_type" in data:
                return True
        except (json.JSONDecodeError, AttributeError):
            pass
        return False

    async def _tool_reponse(self, func_result: Any) -> AsyncGenerator[Any, None]:
        """兼容 async return 和 async yield 的结果，统一为异步流"""
        if inspect.isasyncgen(func_result):  # 异步生成器
            async for item in func_result:
                yield item
        elif inspect.iscoroutine(func_result):  # 协程对象
            result = await func_result
            yield result
        else:  # 普通值
            yield func_result
            
    async def _run(self):
        """运行Agent主逻辑，需在子类中实现"""
        while self.current_round < self.max_rounds:
            self.current_round += 1

            # 检查是否需要压缩内存
            if self.should_compress_memory():
                logger.info("Token使用量超过阈值，开始压缩对话历史...")
                compression_success = await self.compress_conversation_history()
                if compression_success:
                    yield f"\n🗜️ **LLM内存压缩完成**: 当前Token数: {self.current_token_count}\n"
                else:
                    yield f"\n⚠️ **LLM内存压缩失败**: 当前Token数: {self.current_token_count}\n"

            # 计算并记录当前Token使用情况
            current_tokens = self.calculate_current_tokens()
            token_usage_ratio = current_tokens / self.max_context_tokens if self.max_context_tokens > 0 else 0

            logger.info(
                "\n=== Agent Execution Info ===\n"
                f"Agent ID        : {self.agent_id}\n"
                f"Agent Name      : {self.agent_name}\n"
                f"Execution Round : {self.current_round}\n"
                f"Current Tokens  : {current_tokens}\n"
                f"Max Tokens      : {self.max_context_tokens}\n"
                f"Token Usage     : {token_usage_ratio:.2%}\n"
                "============================"
            )

            tool_calls = []
            content_parts = ""
            async for chunk in await self.llm.generate(messages=self.memory.states[self.agent_id]["all_history"], tools=self.tools):
                if chunk.content:
                    content_parts += chunk.content
                    if self.file_operation_tool.is_active():
                        await self.file_operation_tool.write_chunk(chunk.content)
                    # 统一输出结构：普通Agent内容
                    yield AgentStreamPayload(
                        event_type=AgentEventType.AGENT_CONTENT,
                        agent_id=self.agent_id,
                        agent_name=self.agent_name,
                        session_id=self.session_id,
                        current_round=self.current_round,
                        content=chunk.content,
                    ).to_json()
                if chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)

            if content_parts:
                # 计算内容Token数量并添加到元数据
                content_tokens = self.token_counter.count_text_tokens(content_parts)
                self.memory.states[self.agent_id]["all_history"].append(
                    Message(
                        role=MessageRole.ASSISTANT, content=content_parts,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        metadata={"current_round": self.current_round, "tokens": content_tokens}
                    )
                )
            if tool_calls:
                async for chunk in self.execute_tools(tool_calls=tool_calls):
                    yield chunk

            if self.state == AgentState.FINISHED:
                break
            
            # # 为了方便测试
            # if self.agent_name == "PlanAgent":
            #     try:
            #         all_history = self.memory.states[self.agent_id]["all_history"]
            #         saved_path = save_history_to_file(
            #             agent_id=self.agent_id,
            #             agent_name=self.agent_name,
            #             task="",
            #             all_history=all_history,
            #         )
            #         logger.info(f"Agent执行完成，历史记录已保存: {saved_path}")
            #     except Exception as e:
            #         logger.error(f"保存历史记录时出错: {e}")
    
    
    @abstractmethod
    async def run(self):
        """生成响应"""
        pass


