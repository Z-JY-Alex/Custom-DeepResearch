"""
Agent基类模块：提供agent创建、prompt管理、工具使用和执行控制功能
"""

from datetime import datetime
import json
import os
from pathlib import Path
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

CURRENT_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# 获取项目根目录（从当前文件向上三级：backend/agent/ -> backend/ -> project root）
DEFAULT_WORKDIR = str(Path(__file__).parent.parent.parent.absolute())

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
    current_time: Optional[str] = Field(default=CURRENT_TIME, description="当前时间")

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
    
    # 用户交互相关
    interaction_manager: Optional[Any] = Field(default=None, description="交互管理器")
    user_interaction_tool: Optional[Any] = Field(default=None, description="用户交互工具")

    # Token计算
    token_counter: TokenCounter = TokenCounter("gpt-4o")

    # Token管理配置
    max_context_tokens: int = Field(default=200000, description="最大上下文Token数")
    compression_threshold: float = Field(default=0.80, description="触发压缩的Token使用率阈值")
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
        self.artifact_tool = ArtifactWriteTool(
            artifact_manager=self.artifact_manager,
            session_id=self.session_id
            )
        self.terminate = Terminate()

        # self.add_tool(self.file_create_tool)
        self.add_tool(self.file_operation_tool)
        self.add_tool(self.file_read_tool)
        self.add_tool(self.artifact_tool)
        self.add_tool(self.terminate)
        
        # 初始化用户交互工具
        self._init_user_interaction_tool()

    def _init_user_interaction_tool(self):
        """初始化用户交互工具"""
        if self.interaction_manager and self.session_id:
            try:
                from backend.tools.user_interaction import UserInteractionTool
                self.user_interaction_tool = UserInteractionTool(
                    interaction_manager=self.interaction_manager,
                    session_id=self.session_id
                )
                self.add_tool(self.user_interaction_tool)
                logger.info(f"Agent {self.agent_name} 已启用用户交互功能")
            except ImportError as e:
                logger.warning(f"无法导入用户交互工具: {e}")
        else:
            logger.debug(f"Agent {self.agent_name} 未配置用户交互功能")
    
    def enable_user_interaction(self, interaction_manager, session_id: str):
        """启用用户交互功能"""
        self.interaction_manager = interaction_manager
        self.session_id = session_id
        self._init_user_interaction_tool()
        
    def disable_user_interaction(self):
        """禁用用户交互功能"""
        if self.user_interaction_tool:
            self.remove_tool("ask_user")
            self.user_interaction_tool = None
        self.interaction_manager = None
        self.session_id = None
        logger.info(f"Agent {self.agent_name} 已禁用用户交互功能")
        
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
    
    
    async def _compress_tool_result_if_needed(self, tool_result: str, tool_name: str, token_threshold: int = 2000) -> str:
        """
        检查工具结果的Token量，如果超过阈值则进行压缩

        Args:
            tool_result: 工具执行的结果
            tool_name: 工具名称
            token_threshold: Token阈值，默认2000

        Returns:
            压缩后的结果或原始结果
        """
        # 计算工具结果的token数量
        result_tokens = self.token_counter.count_text_tokens(tool_result)

        logger.debug(f"工具 {tool_name} 结果Token数: {result_tokens}")

        # 如果未超过阈值，直接返回原始结果
        if result_tokens <= token_threshold:
            logger.debug(f"工具 {tool_name} 结果未超过阈值({token_threshold})，直接返回")
            return tool_result

        # 超过阈值，进行压缩
        logger.info(f"工具 {tool_name} 结果超过阈值({result_tokens} > {token_threshold})，开始压缩")

        try:
            # 构建压缩提示
            compression_prompt = f"""请压缩以下工具执行结果，保留关键信息：

工具名称: {tool_name}
原始结果长度: {len(tool_result)} 字符
Token数量: {result_tokens}

要求：
1. 保留核心信息和关键数据
2. 去除冗余内容
3. 保持结果可读性
"""

            # 使用LLM进行压缩
            compression_messages = [
                Message(
                    role=MessageRole.SYSTEM,
                    content=compression_prompt,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ),
                Message(
                    role=MessageRole.USER,
                    content=f"原始结果: \n```{tool_result}```\n\n压缩后的结果: \n",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            ]

            compressed_result = ""
            async for chunk in await self.llm.generate(messages=compression_messages, tools=[]):
                if chunk.content:
                    compressed_result += chunk.content

            # 检查压缩后的token数量
            compressed_tokens = self.token_counter.count_text_tokens(compressed_result)
            logger.info(
                f"工具 {tool_name} 结果压缩完成: {result_tokens} -> {compressed_tokens} tokens "
                f"(压缩率: {(1 - compressed_tokens/result_tokens)*100:.1f}%)"
            )

            # 添加压缩标记
            return f"<TOOL_RESULT>由于结果内容过多，需要进行压缩，压缩后的结果：{compressed_result}</TOOL_RESULT>"

        except Exception as e:
            logger.error(f"工具结果压缩失败: {e}，返回截断的原始结果")
            # 如果压缩失败，返回截断的原始结果
            max_chars = int(token_threshold * 3)  # 粗略估计：1 token ≈ 3 字符
            truncated = tool_result[:max_chars]
            return f"[截断] {truncated}... [原始长度: {len(tool_result)} 字符]"

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
                
            # 检查并压缩工具结果（如果需要）
            processed_tool_res = await self._compress_tool_result_if_needed(
                tool_result=cur_tool_res,
                tool_name=function_name,
                token_threshold=10000  # 可以根据需要调整阈值
            )

            messages.append(
                Message(
                    role=MessageRole.TOOL, content=processed_tool_res,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tool_call_id=tool_calls[i].id,
                    metadata={
                        "current_round": self.current_round,
                        "original_length": len(cur_tool_res),
                        "processed_length": len(processed_tool_res),
                        "compressed": len(processed_tool_res) < len(cur_tool_res)
                    }
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
            usage_info = None  # 用于存储真实的token使用情况

            async for chunk in await self.llm.generate(messages=self.memory.states[self.agent_id]["all_history"], tools=self.tools):
                if chunk.content:
                    content_parts += chunk.content
                    if self.file_operation_tool.is_active():
                        await self.file_operation_tool.write_chunk(chunk)
                    yield chunk.content
                if chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)

                # 收集usage信息（通常在最后一个chunk中）
                if chunk.metadata and "usage" in chunk.metadata:
                    usage_info = chunk.metadata["usage"]

            if content_parts:
                # 使用真实的Token数量，如果没有则回退到计算值
                if usage_info and "completion_tokens" in usage_info:
                    content_tokens = usage_info["completion_tokens"]
                    logger.info(f"使用真实Token统计 - completion_tokens: {content_tokens}, "
                               f"prompt_tokens: {usage_info.get('prompt_tokens', 'N/A')}, "
                               f"total_tokens: {usage_info.get('total_tokens', 'N/A')}")
                else:
                    # 回退到估算值
                    content_tokens = self.token_counter.count_text_tokens(content_parts)
                    logger.warning(f"未获取到真实Token统计，使用估算值: {content_tokens}")

                # 构建metadata，包含真实的usage信息
                message_metadata = {
                    "current_round": self.current_round,
                    "tokens": content_tokens
                }
                if usage_info:
                    message_metadata["usage"] = usage_info

                self.memory.states[self.agent_id]["all_history"].append(
                    Message(
                        role=MessageRole.ASSISTANT, content=content_parts,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        metadata=message_metadata
                    )
                )
                if self.agent_name == "PlanAgent":
                    self.memory.states[self.agent_id]["all_history"].append(
                        Message(
                            role=MessageRole.ASSISTANT, 
                            content="请继续按照计划进行执行，严禁跳过或合并计划步骤，不得以'由于时间和篇幅限制'等理由直接跳到最后一步",
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            metadata={"current_round": self.current_round, "tokens": 0}
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
