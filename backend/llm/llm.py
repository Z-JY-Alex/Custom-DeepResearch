"""
LLM模块：支持流式输出和多模态的语言模型接口
"""
import asyncio
import json
import os
from typing import Dict, List, Optional, Union, AsyncGenerator, Any
from loguru import logger
from openai import AsyncOpenAI

# 导入基础类和数据模型
from .base import (
    BaseLLM,
    Message,
    MessageRole,
    ContentType,
    MediaContent,
    LLMConfig,
    StreamChunk,
    create_text_message,
    create_tool_message,
    create_assistant_message_with_tool_calls,
    create_image_content,
    create_message,
)

# 导入工具相关类
from backend.tools.base import ToolFunction, ToolCall

# 导入异常类
from .exceptions import (
    LLMException,
    RateLimitException,
    AuthenticationException,
    ValidationException,
    ToolException,
    ModelNotSupportedException,
    TokenLimitException,
    NetworkException
)


class OpenAILLM(BaseLLM):
    """OpenAI LLM实现"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._initialize_client()
    
    def _initialize_client(self):

        # 获取API密钥
        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise AuthenticationException("未提供OpenAI API密钥，请设置OPENAI_API_KEY环境变量或在配置中提供api_key")
        
        # 初始化客户端
        client_kwargs = {
            "api_key": api_key,
            "timeout": self.config.timeout,
        }
        
        # 如果提供了自定义base_url，使用它
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url or os.getenv("OPENAI_BASE_URL")
        
        try:
            self.client = AsyncOpenAI(**client_kwargs)
            logger.info(f"OpenAI客户端初始化成功，模型: {self.config.model_name}")
        except Exception as e:
            logger.error(f"OpenAI客户端初始化失败: {e}")
            raise LLMException(f"OpenAI客户端初始化失败: {str(e)}")
    
    def is_client_available(self) -> bool:
        """检查OpenAI客户端是否可用"""
        return self.client is not None
    
    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[ToolFunction]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> Union[str, AsyncGenerator[StreamChunk, None]]:
        """生成响应"""
        self.validate_messages(messages)
        
        # 使用配置中的工具或传入的工具
        tools = tools or self.config.tools
        tool_choice = tool_choice or self.config.tool_choice
        
        if self.config.stream:
            return self.generate_stream(messages, tools=tools, tool_choice=tool_choice, **kwargs)
        else:
            return await self._generate_non_stream(messages, tools=tools, tool_choice=tool_choice, **kwargs)
    
    async def _generate_non_stream(self, messages: List[Message], tools: Optional[List[ToolFunction]] = None, tool_choice: Optional[Union[str, Dict[str, Any]]] = None, **kwargs) -> str:
        """非流式生成"""
        try:
            # 构建API消息格式
            api_messages = self._convert_messages_to_api_format(messages)
            
            # 构建API调用参数
            api_params = {
                "model": self.config.model_name,
                "messages": api_messages,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "stream": False,
                **kwargs
            }
            
            # 添加工具参数
            if tools:
                api_params["tools"] = [tool.to_param() for tool in tools]
                if tool_choice:
                    api_params["tool_choice"] = tool_choice
            
            # 调用OpenAI API
            response = await self.client.chat.completions.create(**api_params)
            
            if not response.choices:
                raise LLMException("API返回的响应中没有选择项")
            
            choice = response.choices[0]
            message = choice.message
            
            # 处理工具调用
            if message.tool_calls:
                # 返回包含工具调用信息的特殊格式
                tool_calls = [ToolCall.from_openai_tool_call(tc) for tc in message.tool_calls]
                return json.dumps({
                    "content": message.content or "",
                    "tool_calls": [{"id": tc.id, "type": tc.type, "function": tc.function} for tc in tool_calls]
                })
            
            content = message.content
            if content is None:
                raise LLMException("API返回的内容为空")
            
            return content
            
        except Exception as e:
            logger.error(f"生成响应时出错: {e}")
            self._handle_openai_exception(e)
    
    async def generate_stream(
        self,
        messages: List[Message],
        tools: Optional[List[ToolFunction]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式生成响应"""
        
        try:
            # 构建API消息格式
            api_messages = self._convert_messages_to_api_format(messages)
            
            # 构建API调用参数
            api_params = {
                "model": self.config.model_name,
                "messages": api_messages,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                # "top_p": self.config.top_p,
                "stream": True,
                **kwargs
            }
            
            # 添加工具参数
            if tools:
                api_params["tools"] = [tool.to_param() for tool in tools]
                if tool_choice:
                    api_params["tool_choice"] = tool_choice
            
            # 调用OpenAI流式API
            stream = await self.client.chat.completions.create(**api_params)
            
            chunk_index = 0
            collected_tool_calls = {}  # 使用字典按 index 存储
            
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason
                     
                    # 处理工具调用
                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            # 获取 index，如果没有则默认为 0
                            index = getattr(tool_call, 'index', 0)
                            
                            # 如果这个 index 的工具调用还不存在，初始化它
                            if index not in collected_tool_calls:
                                collected_tool_calls[index] = {
                                    "id": "",
                                    "type": "",
                                    "function": {
                                        "name": "",
                                        "arguments": ""
                                    }
                                }
                            
                            # 累积工具调用信息
                            if tool_call.id:
                                collected_tool_calls[index]["id"] = tool_call.id
                            if tool_call.type:
                                collected_tool_calls[index]["type"] = tool_call.type
                            if tool_call.function:
                                if tool_call.function.name:
                                    collected_tool_calls[index]["function"]["name"] = tool_call.function.name
                                if tool_call.function.arguments:
                                    # 累积拼接 arguments
                                    collected_tool_calls[index]["function"]["arguments"] += tool_call.function.arguments
                    
                    # 检查是否有内容
                    if delta.content is not None:
                        yield StreamChunk(
                            content=delta.content,
                            is_complete=finish_reason is not None,
                            metadata={
                                "chunk_index": chunk_index,
                                "finish_reason": finish_reason,
                                "model": chunk.model if hasattr(chunk, 'model') else self.config.model_name
                            }
                        )
                        chunk_index += 1
                    
                    # 如果流结束，发送完成信号
                    if finish_reason is not None:
                        # 创建工具调用对象
                        tool_calls_obj = None
                        if collected_tool_calls:
                            tool_calls_obj = []
                            # 按 index 顺序处理收集的工具调用
                            for index in sorted(collected_tool_calls.keys()):
                                tc_data = collected_tool_calls[index]
                                if tc_data["id"]:  # 只有当ID存在时才添加
                                    tool_calls_obj.append(ToolCall(
                                        id=tc_data["id"],
                                        type=tc_data["type"],
                                        function=tc_data["function"]
                                    ))
                        
                        yield StreamChunk(
                            content="",
                            is_complete=True,
                            tool_calls=tool_calls_obj,
                            metadata={
                                "chunk_index": chunk_index,
                                "finish_reason": finish_reason,
                                "total_chunks": chunk_index
                            }
                        )
                
        except Exception as e:
            logger.error(f"流式生成时出错: {e}")
            self._handle_openai_exception(e)
    
    def _convert_messages_to_api_format(self, messages: List[Message]) -> List[Dict]:
        """将消息转换为API格式"""
        api_messages = []
        
        for msg in messages:
            api_msg = {"role": msg.role.value}
            
            # 处理工具响应消息
            if msg.role == MessageRole.TOOL:
                api_msg["content"] = msg.content if isinstance(msg.content, str) else str(msg.content)
                if msg.tool_call_id:
                    api_msg["tool_call_id"] = msg.tool_call_id
            else:
                # 处理普通消息内容
                if isinstance(msg.content, str) and msg.content:
                    api_msg["content"] = msg.content
                elif isinstance(msg.content, list):
                    # 处理多模态内容
                    content_parts = []
                    for item in msg.content:
                        if isinstance(item, str):
                            content_parts.append({"type": "text", "text": item})
                        elif isinstance(item, MediaContent):
                            if item.content_type == ContentType.IMAGE:
                                content_parts.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{item.mime_type};base64,{item.to_base64()}"
                                    }
                                })
                            elif item.content_type == ContentType.TEXT:
                                content_parts.append({"type": "text", "text": str(item.data)})
                    
                    api_msg["content"] = content_parts
                
                # 添加工具调用信息
                if msg.tool_calls:
                    api_msg["tool_calls"] = []
                    for tool_call in msg.tool_calls:
                        api_msg["tool_calls"].append({
                            "id": tool_call.id,
                            "type": tool_call.type,
                            "function": tool_call.function
                        })
            
            api_messages.append(api_msg)
        
        return api_messages
    
    def _handle_openai_exception(self, e: Exception) -> None:
        """统一处理OpenAI异常"""
        error_str = str(e).lower()
        
        # 处理OpenAI库的特定异常
        if hasattr(e, '__class__'):
            exception_name = e.__class__.__name__.lower()
            
            # 速率限制
            if 'ratelimit' in exception_name or 'rate_limit' in error_str:
                # 尝试从异常中提取重试时间
                retry_after = getattr(e, 'retry_after', None)
                if retry_after is None:
                    # 从错误消息中解析重试时间
                    import re
                    match = re.search(r'retry after (\d+)', error_str)
                    if match:
                        retry_after = int(match.group(1))
                
                raise RateLimitException(
                    f"API速率限制: {str(e)}",
                    retry_after=retry_after
                )
            
            # 认证错误
            elif 'authentication' in exception_name or any(word in error_str for word in ['authentication', 'unauthorized', 'invalid_api_key', 'api_key']):
                raise AuthenticationException(
                    f"API认证失败: {str(e)}",
                    auth_type="api_key"
                )
            
            # Token限制
            elif 'token' in error_str and ('limit' in error_str or 'exceeded' in error_str):
                # 尝试解析token信息
                import re
                current_match = re.search(r'(\d+)\s*tokens?', error_str)
                max_match = re.search(r'maximum.*?(\d+)', error_str)
                
                current_tokens = int(current_match.group(1)) if current_match else 0
                max_tokens = int(max_match.group(1)) if max_match else self.config.max_tokens
                
                raise TokenLimitException(
                    f"Token限制超出: {str(e)}",
                    current_tokens=current_tokens,
                    max_tokens=max_tokens
                )
            
            # 网络相关错误
            elif any(word in exception_name for word in ['timeout', 'connection', 'network']):
                is_timeout = 'timeout' in exception_name
                status_code = getattr(e, 'status_code', None)
                
                raise NetworkException(
                    f"网络错误: {str(e)}",
                    status_code=status_code,
                    is_timeout=is_timeout
                )
            
            # 模型不支持
            elif 'model' in error_str and ('not found' in error_str or 'unavailable' in error_str):
                raise ModelNotSupportedException(
                    f"模型不可用: {str(e)}",
                    model_name=self.config.model_name
                )
        
        # 默认LLM异常
        raise LLMException(f"LLM调用失败: {str(e)}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model_name": self.config.model_name,
            "supports_tools": self.supports_tools(),
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": self.config.stream
        }
