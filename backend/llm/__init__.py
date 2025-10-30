"""
LLM模块：支持流式输出和多模态的语言模型接口
"""

# 从 base 导入基础类和数据模型
from .base import (
    BaseLLM,
    Message,
    MediaContent,
    StreamChunk,
    LLMConfig,
    MessageRole,
    ContentType,
    create_message,
    create_text_message,
    create_image_content,
    create_tool_message,
    create_assistant_message_with_tool_calls,
)

# 从 llm 导入具体实现
from .llm import OpenAILLM

# 从 token_counter 导入Token计数器
from .token_counter import (
    TokenCounter,
    create_token_counter,
    count_message_tokens,
    count_messages_tokens,
)

from .exceptions import (
    # 异常类
    LLMException,
    RateLimitException,
    AuthenticationException,
    ValidationException,
    ToolException,
    ModelNotSupportedException,
    TokenLimitException,
    NetworkException,
)

__all__ = [
    # 核心类
    "BaseLLM",
    "OpenAILLM",
    "TokenCounter",
    
    # 数据类
    "Message",
    "MediaContent",
    "StreamChunk",
    "LLMConfig",
    
    # 枚举
    "MessageRole",
    "ContentType",
    
    # 异常类
    "LLMException",
    "RateLimitException",
    "AuthenticationException",
    "ValidationException",
    "ToolException",
    "ModelNotSupportedException",
    "TokenLimitException",
    "NetworkException",
    
    # 便捷函数
    "create_message",
    "create_text_message",
    "create_image_content",
    "create_tool_function",
    "create_tool_message",
    "create_assistant_message_with_tool_calls",
    
    # Token计数相关函数
    "create_token_counter",
    "count_message_tokens",
    "count_messages_tokens",
]

__version__ = "1.0.0"
__author__ = "JY.Zhu"
__description__ = "支持流式输出和多模态的语言模型接口"