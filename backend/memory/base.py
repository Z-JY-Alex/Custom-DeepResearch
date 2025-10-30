"""
Memory基类模块：提供记忆管理、Token统计等基础功能
"""

import json
import uuid
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from loguru import logger

from pydantic import BaseModel, Field

# 导入相关模块
from backend.llm.base import MessageRole, Message
from backend.llm.token_counter import TokenCounter, create_token_counter
from backend.agent.schema import AgentState, AgentTypes
from backend.llm.llm import OpenAILLM
from backend.llm.base import LLMConfig


class MemoryItem(BaseModel):
    """记忆项数据类"""
    role: MessageRole = Field(..., description="角色")
    content: str = Field(..., description="内容")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    token_count: int = Field(default=0, description="Token数量")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    class Config:
        arbitrary_types_allowed = True
    
    def get_content_str(self) -> str:
        """获取内容的字符串表示"""
        if isinstance(self.content, str):
            return self.content
        else:
            return json.dumps(self.content, ensure_ascii=False, default=str)


class BaseMemory(BaseModel):
    """
    记忆基类
    对话记忆(conversion_memory): 用户问题和接收到的答案。
    上下文记忆(contexts): 任务执行过程中的全部记忆
    Agent记忆(states): 单个Agent执行的记忆，由Agent自己添加。
    压缩记忆(compress_memory): 整体压缩后的记忆，达到一定条件后自动压缩。
    """

    # 对话记忆
    conversation_memory: List[MemoryItem] = Field(default_factory=list, description="对话记忆")

    # 上下文管理 - 总的context[list]
    contexts: List[MemoryItem] = Field(default_factory=dict, description="上下文字典")

    # Token计数器
    token_counter: TokenCounter = Field(default_factory=lambda: create_token_counter(), description="Token计数器")

    # LLM配置用于压缩
    compression_llm: Optional[OpenAILLM] = Field(default=None, description="用于压缩的LLM实例")
    compression_llm_config: Optional[LLMConfig] = Field(default=None, description="压缩LLM配置")

    # Agent执行状态和结果
    states: Dict[str, Any] = Field(default_factory=dict, description="Agent记忆")

    # 压缩后的记忆
    compressed_memory: List[MemoryItem] = Field(default_factory=list, description="压缩后的记忆")

    # 压缩次数
    total_compressions: int = Field(default=0, description="总压缩次数")

    # 时间戳
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 初始化压缩用的LLM（如果没有提供配置，使用默认配置）
        if self.compression_llm is None:
            if self.compression_llm_config is None:
                # 使用默认配置创建一个轻量级的LLM用于压缩
                self.compression_llm_config = LLMConfig(
                    model_name="gpt-4o-mini",  # 使用更便宜的模型进行压缩
                    temperature=0.3,
                    max_tokens=1000,
                    timeout=30.0
                )
            self.compression_llm = OpenAILLM(self.compression_llm_config)
    
    
    def _add_memory(self):
        """添加记忆"""
        pass
    
    def add_conversation_memory(
        self, role: str, 
        content: Union[str, Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """添加对话记忆"""
        pass
    
    
    def get_conversation_memory(self, limit: Optional[int] = None) -> List[MemoryItem]:
        """获取对话记忆"""
        pass
    
    def compress_memory(self) -> bool:
        """压缩记忆 达到一定条件自动触发"""
        pass
    
    def get_compress_memory(self):
        """获取当前压缩记忆"""
        pass

    def add_contexts_memory(self):
        """添加上下文记忆"""
        pass

    def get_contexts_memory(self):
        """获取上下文记忆"""
        pass

    def calculate_agent_tokens(self, agent_id: str) -> int:
        """计算指定Agent的Token数量"""
        if agent_id not in self.states:
            return 0

        all_history = self.states[agent_id].get("all_history", [])
        if not all_history:
            return 0

        try:
            token_stats = self.token_counter.count_messages_tokens(all_history)
            return token_stats["total_tokens"]
        except Exception as e:
            logger.error(f"Token计算失败: {e}")
            return 0

    def should_compress_agent_memory(
        self,
        agent_id: str,
        max_context_tokens: int,
        compression_threshold: float
    ) -> bool:
        """判断指定Agent是否需要压缩内存"""
        current_tokens = self.calculate_agent_tokens(agent_id)
        threshold_tokens = max_context_tokens * compression_threshold

        logger.debug(f"Agent {agent_id} - 当前Token数: {current_tokens}, 阈值: {threshold_tokens}")
        return current_tokens > threshold_tokens

    async def compress_agent_conversation_history(
        self,
        agent_id: str,
        preserve_initial_rounds: int = 3,
        preserve_recent_rounds: int = 5
    ) -> bool:
        """
        智能压缩指定Agent的对话历史
        保留开始几轮和最近几轮对话，压缩中间部分
        """
        if agent_id not in self.states:
            logger.warning(f"未找到Agent {agent_id} 的对话历史")
            return False

        all_history = self.states[agent_id].get("all_history", [])
        if len(all_history) <= (preserve_initial_rounds + preserve_recent_rounds):
            logger.info(f"Agent {agent_id} 对话轮数太少，无需压缩")
            return False

        try:
            # 分离要保留的和要压缩的消息
            initial_messages = all_history[:preserve_initial_rounds]
            recent_messages = all_history[-preserve_recent_rounds:]
            middle_messages = all_history[preserve_initial_rounds:-preserve_recent_rounds]

            if not middle_messages:
                logger.info(f"Agent {agent_id} 中间消息为空，无需压缩")
                return False

            # 使用LLM压缩中间消息
            logger.info(f"开始使用LLM压缩Agent {agent_id} 的 {len(middle_messages)} 条中间消息")
            compressed_summary = await self._compress_messages(middle_messages)

            # 创建压缩后的消息
            compressed_message = Message(
                role=MessageRole.SYSTEM,
                content=f"[LLM压缩摘要] {compressed_summary}",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"compressed": True, "original_count": len(middle_messages), "compression_method": "llm"}
            )

            # 重建历史记录
            new_history = initial_messages + [compressed_message] + recent_messages
            self.states[agent_id]["all_history"] = new_history

            # 更新压缩统计
            self.total_compressions += 1

            logger.info(
                f"Agent {agent_id} LLM内存压缩完成: {len(all_history)} -> {len(new_history)} 条消息, "
                f"压缩次数: {self.total_compressions}"
            )

            return True

        except Exception as e:
            logger.error(f"Agent {agent_id} LLM内存压缩失败: {e}")
            return False

    async def _compress_messages(self, messages: List[Message]) -> str:
        """
        使用LLM智能压缩消息列表为摘要
        提取关键信息，保持上下文连贯性
        """
        if not messages:
            return "[空消息列表]"

        try:
            # 构建对话历史文本
            conversation_text = self._format_messages_for_compression(messages)

            # 构建压缩提示词
            compression_prompt = self._build_compression_prompt(conversation_text, len(messages))

            # 调用LLM进行压缩
            compression_messages = [
                Message(
                    role=MessageRole.USER,
                    content=compression_prompt,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            ]

            # 获取LLM压缩结果
            compressed_summary = ""
            async for chunk in await self.compression_llm.generate(messages=compression_messages, tools=[]):
                if chunk.content:
                    compressed_summary += chunk.content

            # 如果LLM压缩失败，回退到简单压缩
            if not compressed_summary.strip():
                logger.warning("LLM压缩返回空结果，回退到简单压缩")
                return self._fallback_compression(messages)

            # 添加元数据信息
            metadata_info = f"[原始消息数: {len(messages)}, 压缩时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"

            return f"{compressed_summary.strip()} {metadata_info}"

        except Exception as e:
            logger.error(f"LLM压缩失败: {e}，回退到简单压缩")
            return self._fallback_compression(messages)

    def _format_messages_for_compression(self, messages: List[Message]) -> str:
        """将消息列表格式化为便于压缩的文本"""
        formatted_lines = []

        for i, msg in enumerate(messages):
            # 格式化时间戳
            timestamp = msg.timestamp if msg.timestamp else "未知时间"

            # 处理消息内容
            content = str(msg.content) if msg.content else "[空内容]"

            # 格式化消息
            role_map = {
                MessageRole.USER: "用户",
                MessageRole.ASSISTANT: "助手",
                MessageRole.TOOL: "工具",
                MessageRole.SYSTEM: "系统"
            }
            role_text = role_map.get(msg.role, str(msg.role.value))

            formatted_lines.append(f"{i+1}. [{role_text}] {content}")

        return "\n".join(formatted_lines)

    def _build_compression_prompt(self, conversation_text: str, message_count: int) -> str:
        """构建用于压缩的提示词"""
        return f"""请将以下对话历史压缩为简洁的摘要，要求：

1. **保留关键信息**：重要的决策、结果、错误、文件操作等
2. **保持时序逻辑**：按照对话发展的顺序组织内容
3. **突出重点**：优先保留对后续对话有影响的信息
4. **简洁明了**：用简练的语言概括，避免冗余
5. **结构化输出**：使用清晰的段落和要点

请压缩以下 {message_count} 条消息：

```
{conversation_text}
```

压缩摘要："""

    def _fallback_compression(self, messages: List[Message]) -> str:
        """LLM压缩失败时的回退方案"""
        try:
            # 分类消息
            user_messages = []
            assistant_messages = []
            tool_messages = []
            system_messages = []

            for msg in messages:
                if msg.role == MessageRole.USER:
                    user_messages.append(msg.content)
                elif msg.role == MessageRole.ASSISTANT:
                    assistant_messages.append(msg.content)
                elif msg.role == MessageRole.TOOL:
                    tool_messages.append(msg.content)
                elif msg.role == MessageRole.SYSTEM:
                    system_messages.append(msg.content)

            # 构建简单摘要
            summary_parts = []

            if user_messages:
                user_content = " ".join(str(content) for content in user_messages if content)[:200]
                summary_parts.append(f"用户请求: {user_content}...")

            if assistant_messages:
                assistant_content = " ".join(str(content) for content in assistant_messages if content)[:200]
                summary_parts.append(f"助手回复: {assistant_content}...")

            if tool_messages:
                tool_content = " ".join(str(content) for content in tool_messages if content)[:100]
                summary_parts.append(f"工具执行: {tool_content}...")

            if system_messages:
                system_content = " ".join(str(content) for content in system_messages if content)[:100]
                summary_parts.append(f"系统消息: {system_content}...")

            summary_parts.append(f"[简单压缩] 原始消息数: {len(messages)}")

            return " | ".join(summary_parts)

        except Exception as e:
            logger.error(f"回退压缩也失败: {e}")
            return f"[压缩失败] 包含{len(messages)}条消息的对话片段"

    def _extract_key_points(self, contents: List[str], content_type: str) -> str:
        """
        从内容列表中提取关键点
        """
        if not contents:
            return "无内容"

        # 合并内容
        combined_content = " ".join(str(content) for content in contents if content)

        # 如果内容很短，直接返回
        if len(combined_content) <= 200:
            return combined_content

        # 提取关键词和重要信息
        key_points = []

        # 查找重要的实体和操作
        important_patterns = [
            r'文件[路径]*[：:]\s*([^\s]+)',
            r'创建[了]*\s*([^\s]+)',
            r'执行[了]*\s*([^\s]+)',
            r'错误[：:]\s*([^\n]+)',
            r'成功[：:]\s*([^\n]+)',
            r'配置[：:]\s*([^\n]+)',
        ]

        for pattern in important_patterns:
            matches = re.findall(pattern, combined_content)
            key_points.extend(matches[:3])  # 每类最多3个

        # 如果没有提取到关键点，返回截断的内容
        if not key_points:
            return combined_content[:300] + "..." if len(combined_content) > 300 else combined_content

        # 返回关键点摘要
        return f"{content_type}包含: {', '.join(key_points[:5])}"  # 最多5个关键点

    def get_agent_memory_info(self, agent_id: str) -> Dict[str, Any]:
        """获取指定Agent的内存使用情况"""
        if agent_id not in self.states:
            return {
                "agent_id": agent_id,
                "exists": False,
                "message_count": 0,
                "token_count": 0,
                "compressed_count": 0
            }

        all_history = self.states[agent_id].get("all_history", [])
        token_count = self.calculate_agent_tokens(agent_id)

        # 统计压缩消息数量
        compressed_count = sum(
            1 for msg in all_history
            if msg.metadata and msg.metadata.get("compressed", False)
        )

        return {
            "agent_id": agent_id,
            "exists": True,
            "message_count": len(all_history),
            "token_count": token_count,
            "compressed_count": compressed_count,
            "total_compressions": self.total_compressions,
            "latest_timestamp": all_history[-1].timestamp if all_history else None
        }

    def reset_agent_memory(self, agent_id: str) -> bool:
        """重置指定Agent的内存"""
        if agent_id in self.states:
            self.states[agent_id]["all_history"] = []
            logger.info(f"Agent {agent_id} 内存已重置")
            return True
        return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """获取整体内存统计信息"""
        total_agents = len(self.states)
        total_messages = sum(
            len(state.get("all_history", []))
            for state in self.states.values()
        )
        total_tokens = sum(
            self.calculate_agent_tokens(agent_id)
            for agent_id in self.states.keys()
        )

        return {
            "total_agents": total_agents,
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "total_compressions": self.total_compressions,
            "conversation_memory_items": len(self.conversation_memory),
            "compressed_memory_items": len(self.compressed_memory),
            "timestamp": self.timestamp
        }