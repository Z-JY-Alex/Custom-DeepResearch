"""
LLM基础类和数据模型定义
"""
import base64
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, AsyncGenerator, Any
from enum import Enum
from pydantic import BaseModel, Field

# 导入工具相关类
from backend.tools.base import ToolFunction, ToolCall

# 导入异常类
from .exceptions import (
    ValidationException,
    ModelNotSupportedException,
)

class MessageRole(Enum):
    """消息角色枚举"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContentType(Enum):
    """内容类型枚举"""
    TEXT = "text"
    IMAGE = "image"


class MediaContent(BaseModel):
    """多媒体内容数据类"""
    content_type: ContentType = Field(..., description="内容类型")
    data: Union[str, bytes] = Field(..., description="内容数据")
    mime_type: Optional[str] = Field(default=None, description="MIME类型")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    
    class Config:
        arbitrary_types_allowed = True
    
    def to_base64(self) -> str:
        """将内容转换为base64编码"""
        if isinstance(self.data, str):
            return base64.b64encode(self.data.encode()).decode()
        return base64.b64encode(self.data).decode()


class Message(BaseModel):
    """消息数据类"""
    role: MessageRole = Field(..., description="消息角色")
    content: Union[str, List[Union[str, MediaContent]]] = Field(..., description="消息内容")
    timestamp: Optional[str] = Field(default=None, description="时间戳")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    tool_calls: Optional[List[ToolCall]] = Field(default=None, description="工具调用列表")
    tool_call_id: Optional[str] = Field(default=None, description="工具调用ID")
    
    class Config:
        arbitrary_types_allowed = True
    
    def has_media(self) -> bool:
        """检查消息是否包含多媒体内容"""
        if isinstance(self.content, list):
            return any(isinstance(item, MediaContent) for item in self.content)
        return False
    
    def has_tool_calls(self) -> bool:
        """检查消息是否包含工具调用"""
        return self.tool_calls is not None and len(self.tool_calls) > 0
    
    def is_tool_response(self) -> bool:
        """检查是否为工具响应消息"""
        return self.role == MessageRole.TOOL and self.tool_call_id is not None


class LLMConfig(BaseModel):
    """LLM配置数据类"""
    model_name: str = Field(default="MaaS_Sonnet_4", description="模型名称")
    api_key: Optional[str] = Field(default=None, description="API密钥")
    base_url: Optional[str] = Field(default=None, description="基础URL")
    max_tokens: int = Field(default=1000000, description="最大token数")
    temperature: float = Field(default=0.7, description="温度参数")
    top_p: float = Field(default=1.0, description="Top-p参数")
    stream: bool = Field(default=True, description="是否使用流式输出")
    timeout: int = Field(default=120, description="超时时间")
    retry_attempts: int = Field(default=3, description="重试次数")
    supports_vision: bool = Field(default=False, description="是否支持视觉")
    supports_audio: bool = Field(default=False, description="是否支持音频")
    tools: Optional[List[ToolFunction]] = Field(default=None, description="工具列表")
    tool_choice: Optional[Union[str, Dict[str, Any]]] = Field(default=None, description="工具选择")
    
    class Config:
        arbitrary_types_allowed = True


class StreamChunk(BaseModel):
    """流式输出数据块"""
    content: str = Field(..., description="内容")
    is_complete: bool = Field(default=False, description="是否完成")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数据")
    tool_calls: Optional[List[ToolCall]] = Field(default=None, description="工具调用列表")
    
    class Config:
        arbitrary_types_allowed = True


class BaseLLM(ABC):
    """LLM基础抽象类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        
    @abstractmethod
    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolFunction]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[str, AsyncGenerator[StreamChunk, None]]:
        """生成响应"""
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolFunction]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式生成响应"""
        pass
    
    def supports_tools(self) -> bool:
        """检查是否支持工具调用"""
        return True  # 默认支持，子类可以重写
    
    def validate_messages(self, messages: List[Message]) -> bool:
        """验证消息格式"""
        if not messages:
            raise ValidationException("消息列表不能为空", field="messages")
        
        for i, msg in enumerate(messages):
            if not isinstance(msg.role, MessageRole):
                raise ValidationException(
                    f"消息 {i} 的角色类型无效",
                    field=f"messages[{i}].role",
                    value=msg.role
                )
            
            
            # 检查工具调用支持
            if msg.has_tool_calls() and not self.supports_tools():
                raise ModelNotSupportedException(
                    "当前模型不支持工具调用",
                    model_name=self.config.model_name,
                    feature="function_calling"
                )
        
        return True
    
    def validate_tools(self, tools: Optional[List[ToolFunction]]) -> bool:
        """验证工具定义"""
        if not tools:
            return True
            
        if not self.supports_tools():
            raise ModelNotSupportedException(
                "当前模型不支持工具调用",
                model_name=self.config.model_name,
                feature="function_calling"
            )
        
        for i, tool in enumerate(tools):
            if not isinstance(tool, ToolFunction):
                raise ValidationException(
                    f"工具 {i} 类型无效",
                    field=f"tools[{i}]",
                    value=type(tool).__name__
                )
            
            if not tool.name:
                raise ValidationException(
                    f"工具 {i} 名称不能为空",
                    field=f"tools[{i}].name",
                    value=tool.name
                )
            
            if not tool.description:
                raise ValidationException(
                    f"工具 {i} 描述不能为空",
                    field=f"tools[{i}].description",
                    value=tool.description
                )
        
        return True


# 辅助函数
def create_text_message(role: MessageRole, content: str) -> Message:
    """创建文本消息"""
    return Message(role=role, content=content)


def create_tool_message(tool_call_id: str, content: str) -> Message:
    """创建工具响应消息"""
    return Message(role=MessageRole.TOOL, content=content, tool_call_id=tool_call_id)


def create_assistant_message_with_tool_calls(content: str, tool_calls: List[ToolCall]) -> Message:
    """创建包含工具调用的助手消息"""
    return Message(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls)


def create_image_content(image_data: bytes, mime_type: str = "image/jpeg") -> MediaContent:
    """创建图片内容"""
    return MediaContent(
        content_type=ContentType.IMAGE,
        data=image_data,
        mime_type=mime_type
    )


def create_message(role: MessageRole, content: Union[str, List[Union[str, MediaContent]]]) -> Message:
    """创建消息"""
    return Message(role=role, content=content)