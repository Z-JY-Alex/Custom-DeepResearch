"""
Memory基类模块：提供记忆管理、Token统计等基础功能
"""

import json
import os
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
                    model_name="MaaS_Sonnet_4",  # 使用更便宜的模型进行压缩
                    temperature=0.3,
                    max_tokens=1000,
                    timeout=30.0,
                    api_key="amep3rwbqWIpFoOnKpZw",
                    base_url="https://genaiapish-zy2cw9s.xiaosuai.com/v1"
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
        """
        计算指定Agent的Token数量
        优先使用最近一次LLM调用返回的真实total_tokens，回退到估算值
        """
        if agent_id not in self.states:
            return 0

        all_history = self.states[agent_id].get("all_history", [])
        if not all_history:
            return 0

        try:
            # 从后往前查找最近的真实token统计
            for msg in reversed(all_history):
                if msg.metadata and "usage" in msg.metadata:
                    usage = msg.metadata["usage"]
                    if "total_tokens" in usage:
                        total_tokens = usage["total_tokens"]
                        logger.debug(
                            f"Agent {agent_id} Token统计(真实) - "
                            f"total_tokens: {total_tokens}, "
                            f"completion_tokens: {usage.get('completion_tokens', 'N/A')}, "
                            f"prompt_tokens: {usage.get('prompt_tokens', 'N/A')}"
                        )
                        return  

            # 如果没有找到真实统计，回退到估算所有消息
            logger.debug(f"Agent {agent_id} 未找到真实Token统计，回退到估算")
            token_stats = self.token_counter.count_messages_tokens(all_history)
            total_tokens = token_stats["total_tokens"]
            logger.debug(f"Agent {agent_id} Token统计(估算) - total_tokens: {total_tokens}")
            return total_tokens

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

    def _adjust_compression_range(self, messages: List[Message], start: int, end: int) -> tuple:
        """
        调整压缩范围，避免分割工具调用对
        如果压缩范围刚好分割了工具调用对，则向前或向后调整一位
        返回: (adjusted_start, adjusted_end)
        """
        # 检查起始位置是否在工具调用对中间
        if start > 0 and start < len(messages):
            # 如果start位置是TOOL消息，且前面是ASSISTANT消息，说明分割了工具调用对
            if (messages[start].role == MessageRole.TOOL and 
                messages[start - 1].role == MessageRole.ASSISTANT and 
                messages[start - 1].has_tool_calls()):
                # 向前调整，包含整个工具调用对
                start = start - 1
        
        # 检查结束位置是否在工具调用对中间
        if end >= 0 and end < len(messages) - 1:
            # 如果end位置是ASSISTANT消息，且后面是TOOL消息，说明分割了工具调用对
            if (messages[end].role == MessageRole.ASSISTANT and 
                messages[end].has_tool_calls() and 
                end + 1 < len(messages) and 
                messages[end + 1].role == MessageRole.TOOL):
                # 向后调整，包含整个工具调用对
                end = end + 1
                # 继续向后查找，直到找到所有TOOL消息
                while end + 1 < len(messages) and messages[end + 1].role == MessageRole.TOOL:
                    end = end + 1
        
        return (start, end)

    async def compress_agent_conversation_history(
        self,
        agent_id: str,
        preserve_initial_rounds: int = 3,
        preserve_recent_rounds: int = 5
    ) -> bool:
        """
        智能压缩指定Agent的对话历史
        保留开始几轮和最近几轮对话，压缩中间部分
        确保不会分割工具调用对(tool_use + tool_result)
        """
        if agent_id not in self.states:
            logger.warning(f"未找到Agent {agent_id} 的对话历史")
            return False

        all_history = self.states[agent_id].get("all_history", [])
        if len(all_history) <= (preserve_initial_rounds + preserve_recent_rounds):
            logger.info(f"Agent {agent_id} 对话轮数太少，无需压缩")
            return False

        try:
            # 计算原始压缩范围
            original_start = preserve_initial_rounds
            original_end = len(all_history) - preserve_recent_rounds - 1
            
            if original_start >= original_end:
                logger.info(f"Agent {agent_id} 中间消息为空，无需压缩")
                return False

            # 调整压缩范围，避免分割工具调用对
            adjusted_start, adjusted_end = self._adjust_compression_range(all_history, original_start, original_end)
            
            # 分离要保留的和要压缩的消息
            initial_messages = all_history[:adjusted_start]
            middle_messages = all_history[adjusted_start:adjusted_end + 1]
            recent_messages = all_history[adjusted_end + 1:]

            if not middle_messages:
                logger.info(f"Agent {agent_id} 调整后的压缩范围内无消息，无需压缩")
                return False

            # 使用LLM压缩中间消息
            range_info = f"原始范围: {original_start}-{original_end}, 调整后: {adjusted_start}-{adjusted_end}"
            logger.info(f"开始使用LLM压缩Agent {agent_id} 的 {len(middle_messages)} 条中间消息 ({range_info})")
            compressed_summary = await self._compress_messages(middle_messages)

            # 创建压缩后的消息
            compressed_message = Message(
                role=MessageRole.SYSTEM,
                content=f"[LLM压缩摘要] {compressed_summary}",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={
                    "compressed": True, 
                    "original_count": len(middle_messages), 
                    "compression_method": "llm",
                    "original_range": f"{original_start}-{original_end}",
                    "adjusted_range": f"{adjusted_start}-{adjusted_end}"
                }
            )

            # 重建历史记录
            new_history = initial_messages + [compressed_message] + recent_messages
            self.states[agent_id]["all_history"] = new_history

            # 更新压缩统计
            self.total_compressions += 1

            logger.info(
                f"Agent {agent_id} LLM内存压缩完成: {len(all_history)} -> {len(new_history)} 条消息, "
                f"压缩次数: {self.total_compressions}, {range_info}"
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
            usage_info = None  # 存储真实的token使用情况

            async for chunk in await self.compression_llm.generate(messages=compression_messages, tools=[]):
                if chunk.content:
                    compressed_summary += chunk.content
                # 收集usage信息
                if chunk.metadata and "usage" in chunk.metadata:
                    usage_info = chunk.metadata["usage"]

            # 记录压缩时的token使用情况
            if usage_info:
                logger.info(
                    f"LLM压缩Token使用 - "
                    f"completion_tokens: {usage_info.get('completion_tokens', 'N/A')}, "
                    f"prompt_tokens: {usage_info.get('prompt_tokens', 'N/A')}, "
                    f"total_tokens: {usage_info.get('total_tokens', 'N/A')}"
                )

            # 如果LLM压缩失败，回退到简单压缩
            if not compressed_summary.strip():
                logger.warning("LLM压缩返回空结果，回退到简单压缩")
                return self._fallback_compression(messages)

            # 添加元数据信息
            metadata_info = f"[原始消息数: {len(messages)}, 压缩时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            if usage_info and "total_tokens" in usage_info:
                metadata_info += f", 压缩消耗Token: {usage_info['total_tokens']}"
            metadata_info += "]"

            return f"{compressed_summary.strip()} {metadata_info}"

        except Exception as e:
            logger.error(f"LLM压缩失败: {e}，回退到简单压缩")
            return self._fallback_compression(messages)

    def _format_messages_for_compression(self, messages: List[Message]) -> str:
        """将消息列表格式化为便于压缩的文本"""
        formatted_lines = []

        for i, msg in enumerate(messages):
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

    def validate_message_sequence_for_llm(self, messages: List[Message]) -> bool:
        """
        验证消息序列是否符合LLM API要求，特别是工具调用对的格式
        返回: True 如果格式正确，否则抛出异常
        """
        if not messages:
            return True
        
        i = 0
        while i < len(messages):
            msg = messages[i]
            
            # 检查包含工具调用的ASSISTANT消息
            if msg.role == MessageRole.ASSISTANT and msg.has_tool_calls():
                tool_call_ids = {tc.id for tc in msg.tool_calls}
                expected_tool_responses = len(tool_call_ids)
                found_responses = 0
                
                # 检查后续消息是否为对应的TOOL响应
                j = i + 1
                while j < len(messages) and found_responses < expected_tool_responses:
                    next_msg = messages[j]
                    
                    # 如果遇到非TOOL消息，说明工具调用对被打断
                    if next_msg.role != MessageRole.TOOL:
                        raise ValueError(
                            f"工具调用对被打断: 位置 {i} 的ASSISTANT消息包含工具调用，"
                            f"但位置 {j} 的消息角色为 {next_msg.role.value}，期望为 TOOL"
                        )
                    
                    # 检查tool_call_id是否匹配
                    if next_msg.tool_call_id not in tool_call_ids:
                        raise ValueError(
                            f"工具调用ID不匹配: 位置 {j} 的TOOL消息的tool_call_id '{next_msg.tool_call_id}' "
                            f"不在位置 {i} 的ASSISTANT消息的工具调用ID列表中: {list(tool_call_ids)}"
                        )
                    
                    found_responses += 1
                    j += 1
                
                # 检查是否找到了所有期望的工具响应
                if found_responses < expected_tool_responses:
                    raise ValueError(
                        f"工具调用对不完整: 位置 {i} 的ASSISTANT消息包含 {expected_tool_responses} 个工具调用，"
                        f"但只找到 {found_responses} 个对应的TOOL响应"
                    )
                
                i = j
            else:
                i += 1
        
        return True

    def get_safe_message_history(self, agent_id: str) -> List[Message]:
        """
        获取经过验证的安全消息历史，确保格式符合LLM API要求
        """
        if agent_id not in self.states:
            return []
        
        messages = self.states[agent_id].get("all_history", [])
        
        try:
            # 验证消息序列格式
            self.validate_message_sequence_for_llm(messages)
            return messages
        except ValueError as e:
            logger.error(f"Agent {agent_id} 消息序列格式错误: {e}")
            
            # 尝试修复消息序列
            fixed_messages = self._fix_message_sequence(messages)
            
            try:
                self.validate_message_sequence_for_llm(fixed_messages)
                logger.info(f"Agent {agent_id} 消息序列已修复")
                # 更新修复后的消息历史
                self.states[agent_id]["all_history"] = fixed_messages
                return fixed_messages
            except ValueError as fix_error:
                logger.error(f"Agent {agent_id} 消息序列修复失败: {fix_error}")
                # 返回空列表，强制重新开始对话
                return []

    def _fix_message_sequence(self, messages: List[Message]) -> List[Message]:
        """
        尝试修复消息序列中的工具调用对格式问题
        """
        if not messages:
            return messages
        
        fixed_messages = []
        i = 0
        
        while i < len(messages):
            msg = messages[i]
            fixed_messages.append(msg)
            
            # 如果是包含工具调用的ASSISTANT消息
            if msg.role == MessageRole.ASSISTANT and msg.has_tool_calls():
                tool_call_ids = {tc.id for tc in msg.tool_calls}
                
                # 收集对应的TOOL响应消息
                tool_responses = []
                j = i + 1
                
                while j < len(messages):
                    next_msg = messages[j]
                    
                    # 如果是对应的TOOL响应，收集它
                    if (next_msg.role == MessageRole.TOOL and 
                        next_msg.tool_call_id and 
                        next_msg.tool_call_id in tool_call_ids):
                        tool_responses.append(next_msg)
                        tool_call_ids.discard(next_msg.tool_call_id)
                    # 如果是其他类型的消息，停止收集
                    elif next_msg.role != MessageRole.TOOL:
                        break
                    
                    j += 1
                
                # 添加收集到的TOOL响应
                fixed_messages.extend(tool_responses)
                
                # 跳过已处理的消息
                i = j
            else:
                i += 1
        
        return fixed_messages