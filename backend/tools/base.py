from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Union
from enum import Enum
from typing import Any, AsyncGenerator
import inspect
from pydantic import BaseModel, Field


class ToolType(Enum):
    """工具类型枚举"""
    FUNCTION = "function"


class ToolCall(BaseModel):
    """LLM工具调用信息"""
    id: str = Field(..., description="工具调用ID")
    type: str = Field(..., description="工具调用类型")
    function: Dict[str, Any] = Field(..., description="函数调用信息")
    
    class Config:
        arbitrary_types_allowed = True
    
    @classmethod
    def from_openai_tool_call(cls, tool_call) -> "ToolCall":
        """从OpenAI工具调用对象创建"""
        return cls(
            id=tool_call.id,
            type=tool_call.type,
            function={
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments
            }
        )
        

class ToolFunction(BaseModel):
    """LLM工具函数定义"""
    name: str = Field(..., description="工具函数名称")
    description: str = Field(..., description="工具函数描述")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="工具函数参数")
    parallel: bool = Field(default=False, description="是否并发执行")
    
    class Config:
        arbitrary_types_allowed = True
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（向后兼容）"""
        return self.to_param()
    
    def to_param(self) -> Dict[str, Any]:
        """转换为函数调用格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class BaseTool(ToolFunction):
    """LLM工具函数调用"""

    async def __call__(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        result = self.execute(**kwargs)
        # 兼容 async return / async yield
        async for chunk in self._tool_response(result):
            yield chunk

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        
    async def _tool_response(self, func_result: Any) -> AsyncGenerator[Any, None]:
        """兼容 async return 和 async yield 的结果，统一为异步流"""
        if inspect.isasyncgen(func_result):  # 异步生成器
            async for item in func_result:
                yield item
        elif inspect.iscoroutine(func_result):  # 协程对象
            result = await func_result
            yield result
        else:  # 普通值
            yield func_result


class ToolCallResult(BaseModel):
    """LLM工具调用结果"""
    tool_call_id: str = Field(..., description="工具调用ID")
    result: Optional[str] = Field(default=None, description="执行结果（内部详细结果）")
    user_result: Optional[str] = Field(default=None, description="用户友好的执行结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    output: Optional[Any] = Field(default=None, description="输出内容")
    base64_image: Optional[str] = Field(default=None, description="Base64编码的图片")
    system: Optional[str] = Field(default=None, description="系统信息")
    
    class Config:
        arbitrary_types_allowed = True
    
    def __bool__(self):
        """检查结果是否有效"""
        # 兼容 Pydantic v1 和 v2
        try:
            # Pydantic v2
            field_names = self.model_fields.keys()
        except AttributeError:
            # Pydantic v1
            field_names = self.__fields__.keys()
        
        return any(getattr(self, field_name) for field_name in field_names if field_name != 'tool_call_id')
    
    def __str__(self):
        """字符串表示（默认返回用户友好结果，如无则返回内部结果）"""
        if self.error:
            return f"Error: {self.error} "
        return str(self.user_result or self.result or self.output or "")

    def get_user_output(self) -> str:
        """获取给用户看的结果"""
        if self.error:
            return f"Error: {self.error} "
        return str(self.user_result or self.result or self.output or "")

    def get_internal_output(self) -> str:
        """获取给内部看的详细结果"""
        if self.error:
            return f"Error: {self.error} "
        return str(self.result or self.output or "")
    
    def __add__(self, other: Union["ToolCallResult", str]):
        """合并两个工具调用结果或与字符串相加"""
        if isinstance(other, str):
            # 与字符串相加，返回字符串
            return str(self) + other

        # 与另一个ToolCallResult相加
        def combine_fields(field: Optional[str], other_field: Optional[str], concatenate: bool = True):
            if field and other_field:
                if concatenate:
                    return field + other_field
                raise ValueError("Cannot combine tool results")
            return field or other_field

        return ToolCallResult(
            tool_call_id=self.tool_call_id,
            result=combine_fields(self.result, other.result),
            user_result=combine_fields(self.user_result, other.user_result),
            error=combine_fields(self.error, other.error),
            output=combine_fields(self.output, other.output),
            base64_image=combine_fields(self.base64_image, other.base64_image, False),
            system=combine_fields(self.system, other.system),
        )
    
    def __radd__(self, other: str):
        """支持右侧加法运算（字符串 + ToolCallResult）"""
        if isinstance(other, str):
            return other + str(self)
        return NotImplemented
    
    def replace(self, **kwargs):
        """返回一个新的ToolCallResult，替换指定字段"""
        return type(self)(**{**self.dict(), **kwargs})

class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message
        
    def __str__(self):
        return f"[Failed] [工具调用失败]: {self.message}"
    
    def __radd__(self, other: str):
        """支持右侧加法运算（字符串 + ToolCallResult）"""
        if isinstance(other, str):
            return other + str(self)
        return NotImplemented
    