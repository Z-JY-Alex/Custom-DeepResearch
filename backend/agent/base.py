"""
Agent基类模块：提供agent创建、prompt管理、工具使用和执行控制功能
"""

from datetime import datetime
import json
import uuid
import inspect
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from loguru import logger

from pydantic import BaseModel, Field

# 导入相关模块
from backend.memory.base import BaseMemory
from backend.agent.schema import AgentState
from backend.prompts.base import BasePrompt
from backend.tools.base import BaseTool, ToolFunction
from backend.llm.base import BaseLLM, Message, MessageRole, LLMConfig
from backend.llm.llm import OpenAILLM
from backend.mcp_client import MCPClient
from backend.artifacts.manager import ArtifactManager
from backend.tools.file_operations import FileCreateTool, FileReadTool
# from backend.tools.stream_file_write import 
from backend.tools.stream_file_operations import StreamFileOperationTool
from backend.tools.artifact_write import ArtifactWriteTool
from backend.tools.terminate import Terminate
from backend.llm.token_counter import TokenCounter
from backend.utils.history import save_history_to_file



class BaseAgent(BaseModel, ABC):
    """Agent基类"""
    
    # 基本属性
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Agent ID")
    agent_name: str = Field(..., description="Agent名称")
    agent_description: str = Field(..., description="Agent描述")
    
    # 状态管理
    state: AgentState = Field(default=AgentState.IDLE, description="Agent状态")
    
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

    # Token计算
    token_counter: TokenCounter = TokenCounter("gpt-4o")

    # Token管理配置
    max_context_tokens: int = Field(default=1000000, description="最大上下文Token数")
    compression_threshold: float = Field(default=0.85, description="触发压缩的Token使用率阈值")
    preserve_recent_rounds: int = Field(default=5, description="保留最近N轮对话不压缩")
    preserve_initial_rounds: int = Field(default=5, description="保留开始N轮对话不压缩")
    current_token_count: int = Field(default=0, description="当前Token使用量")

    # 执行配置
    max_rounds: int = Field(default=80, description="最大执行次数，避免死循环")
    current_round: int = Field(default=0, description="当前执行轮数")
    default_timeout: float = Field(default=300.0, description="默认超时时间")
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 初始化LLM
        if self.llm is None and self.llm_config:
            self.llm = OpenAILLM(self.llm_config)
        
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
        """执行工具调用"""
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
        
        for i, tool_call in enumerate(tool_calls):
            function_name = tool_call.function['name']
            arguments = json.loads(tool_call.function['arguments'])
            
            logger.info(f"执行工具: {function_name}")
            yield f"\n<TOOL_CALL> {function_name} </TOOL_CALL>\n"
            yield f"\n<TOOL_ARGS> {str(arguments)[:1000]} </TOOL_ARGS>\n"
            # 根据工具名称获取对应的工具实例
            tool_instance = self.get_tool_by_name(function_name)
            
            if not tool_instance:
                error_msg = f"未找到工具: {function_name}"
                logger.error(error_msg)
                yield f"\n❌ **错误**: {error_msg}\n"
                continue
            
            try:
                cur_tool_res = ""
                yield "\n<TOOL_RESULT>"
                async for chunk in self._tool_reponse(tool_instance(**arguments)):
                    cur_tool_res += chunk
                    yield chunk
                yield "</TOOL_RESULT>\n"
                
                if function_name == "terminate":
                    self.state = AgentState.FINISHED
                    return
                
            except Exception as e:
                cur_tool_res = f"工具执行失败: {str(e)}"
                logger.error(f"{function_name} 执行失败: {e}")
                yield f"\n<TOOL_RESULT> {cur_tool_res} </TOOL_RESULT>\n"
                
            messages.append(
                Message(
                    role=MessageRole.TOOL, content=cur_tool_res,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tool_call_id=tool_calls[i].id,
                    metadata={"current_round": self.current_round}
                )
            )
        self.memory.states[self.agent_id]["all_history"].extend(messages)


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
                        await self.file_operation_tool.write_chunk(chunk)
                    yield chunk.content
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
            
            # 为了方便测试
            if self.agent_name == "PlanAgent":
                try:
                    all_history = self.memory.states[self.agent_id]["all_history"]
                    saved_path = save_history_to_file(
                        agent_id=self.agent_id,
                        agent_name=self.agent_name,
                        task="",
                        all_history=all_history,
                    )
                    logger.info(f"Agent执行完成，历史记录已保存: {saved_path}")
                except Exception as e:
                    logger.error(f"保存历史记录时出错: {e}")
    
    
    @abstractmethod
    async def run(self):
        """生成响应"""
        pass


