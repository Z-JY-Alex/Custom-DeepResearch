"""
Token计数器模块：统计消息的token使用量
"""
import tiktoken
from typing import List, Dict, Optional, Union, Any
from loguru import logger

from .base import Message, MessageRole, MediaContent, ContentType
from .exceptions import ValidationException, LLMException


class TokenCounter:
    """Token计数器类，用于统计消息的token使用量"""
    
    def __init__(self, model_name: str = "gpt-4o"):
        """
        初始化Token计数器
        
        Args:
            model_name: 模型名称，用于选择合适的编码器
        """
        self.model_name = model_name
        self._encoder = None
        self._init_encoder()
    
    def _init_encoder(self):
        """初始化tiktoken编码器"""
        try:
            # 根据模型名称选择合适的编码器
            if "gpt" in self.model_name.lower():
                self._encoder = tiktoken.encoding_for_model("gpt-4")
            elif "claude" in self.model_name.lower():
                # Claude系列使用cl100k_base编码
                self._encoder = tiktoken.get_encoding("cl100k_base")
            else:
                # 默认使用cl100k_base编码
                self._encoder = tiktoken.get_encoding("cl100k_base")
                logger.warning(f"未识别的模型 {self.model_name}，使用默认编码器 cl100k_base")
        except Exception as e:
            logger.error(f"初始化编码器失败: {e}")
            raise LLMException(f"Token编码器初始化失败: {str(e)}")
    
    def count_text_tokens(self, text: str) -> int:
        """
        计算文本的token数量
        
        Args:
            text: 要计算的文本
            
        Returns:
            token数量
        """
        if not text:
            return 0
        
        try:
            return len(self._encoder.encode(text))
        except Exception as e:
            logger.error(f"计算文本token失败: {e}")
            raise ValidationException(f"文本token计算失败: {str(e)}", field="text", value=text)
    
    def count_message_tokens(self, message: Message) -> Dict[str, int]:
        """
        计算单个消息的token使用量
        
        Args:
            message: 要计算的消息
            
        Returns:
            包含各部分token数量的字典
        """
        if not isinstance(message, Message):
            raise ValidationException("输入必须是Message对象", field="message", value=type(message))
        
        result = {
            "role_tokens": 0,
            "content_tokens": 0,
            "tool_call_tokens": 0,
            "metadata_tokens": 0,
            "total_tokens": 0
        }
        
        # 计算角色token
        result["role_tokens"] = self.count_text_tokens(message.role.value)
        
        # 计算内容token
        if isinstance(message.content, str):
            result["content_tokens"] = self.count_text_tokens(message.content)
        elif isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, str):
                    result["content_tokens"] += self.count_text_tokens(item)
                elif isinstance(item, MediaContent):
                    # 对于媒体内容，我们计算其描述性文本的token
                    if item.content_type == ContentType.TEXT:
                        result["content_tokens"] += self.count_text_tokens(str(item.data))
                    elif item.content_type == ContentType.IMAGE:
                        # 图片内容按固定token计算
                        result["content_tokens"] += 768  # 基础图片token消耗
        
        # 计算工具调用token
        if message.tool_calls:
            for tool_call in message.tool_calls:
                result["tool_call_tokens"] += self.count_text_tokens(tool_call.function.get("name", ""))
                result["tool_call_tokens"] += self.count_text_tokens(tool_call.function.get("arguments", ""))
        
        # 计算工具调用ID token
        if message.tool_call_id:
            result["tool_call_tokens"] += self.count_text_tokens(message.tool_call_id)
        
        # 计算元数据token
        if message.metadata:
            metadata_str = str(message.metadata)
            result["metadata_tokens"] = self.count_text_tokens(metadata_str)
        
        # 计算总token（包括消息格式开销）
        result["total_tokens"] = (
            result["role_tokens"] + 
            result["content_tokens"] + 
            result["tool_call_tokens"] + 
            result["metadata_tokens"] +
            3  # 消息格式开销
        )
        
        return result
    
    def count_messages_tokens(self, messages: List[Message]) -> Dict[str, Any]:
        """
        计算消息列表的总token使用量
        
        Args:
            messages: 消息列表
            
        Returns:
            包含总计和详细统计的字典
        """
        if not messages:
            return {
                "total_tokens": 0,
                "message_count": 0,
                "details": [],
                "by_role": {},
                "has_media": False,
                "has_tools": False
            }
        
        total_tokens = 0
        details = []
        by_role = {}
        has_media = False
        has_tools = False
        
        for i, message in enumerate(messages):
            msg_tokens = self.count_message_tokens(message)
            total_tokens += msg_tokens["total_tokens"]
            
            # 记录详细信息
            details.append({
                "index": i,
                "role": message.role.value,
                "tokens": msg_tokens
            })
            
            # 按角色统计
            role = message.role.value
            if role not in by_role:
                by_role[role] = {"count": 0, "tokens": 0}
            by_role[role]["count"] += 1
            by_role[role]["tokens"] += msg_tokens["total_tokens"]
            
            # 检查特殊内容
            if message.has_media():
                has_media = True
            if message.has_tool_calls():
                has_tools = True
        
        return {
            "total_tokens": total_tokens,
            "message_count": len(messages),
            "details": details,
            "by_role": by_role,
            "has_media": has_media,
            "has_tools": has_tools,
            "average_tokens_per_message": total_tokens / len(messages) if messages else 0
        }
    
    def estimate_cost(self, token_count: int, model_name: Optional[str] = None) -> Dict[str, float]:
        """
        根据token数量估算成本
        
        Args:
            token_count: token数量
            model_name: 模型名称（可选，默认使用初始化时的模型）
            
        Returns:
            包含成本信息的字典
        """
        model = model_name or self.model_name
        
        # 模型价格表（每1000个token的价格，单位：美元）
        pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-4": {"input": 0.0015, "output": 0.002},
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        }
        
        # 查找匹配的模型价格
        model_pricing = None
        for model_key in pricing:
            if model_key in model.lower():
                model_pricing = pricing[model_key]
                break
        
        if not model_pricing:
            # 未知模型，使用默认价格
            model_pricing = {"input": 0.002, "output": 0.002}
        
        cost_per_1k = model_pricing["input"]  # 假设是输入token
        estimated_cost = (token_count / 1000) * cost_per_1k
        
        return {
            "token_count": token_count,
            "cost_per_1k_tokens": cost_per_1k,
            "estimated_cost_usd": round(estimated_cost, 6),
            "model": model
        }
    
    def get_token_usage_summary(self, messages: List[Message]) -> Dict[str, Any]:
        """
        获取消息列表的token使用情况汇总
        
        Args:
            messages: 消息列表
            
        Returns:
            完整的token使用汇总信息
        """
        token_stats = self.count_messages_tokens(messages)
        cost_info = self.estimate_cost(token_stats["total_tokens"])
        
        return {
            **token_stats,
            "cost_estimation": cost_info,
            "model_name": self.model_name,
            "encoding": self._encoder.name if self._encoder else "unknown"
        }
    
    def analyze_token_distribution(self, messages: List[Message]) -> Dict[str, Any]:
        """
        分析token在不同部分的分布情况
        
        Args:
            messages: 消息列表
            
        Returns:
            token分布分析结果
        """
        stats = self.count_messages_tokens(messages)
        
        total_content_tokens = 0
        total_tool_tokens = 0
        total_metadata_tokens = 0
        
        for detail in stats["details"]:
            tokens = detail["tokens"]
            total_content_tokens += tokens["content_tokens"]
            total_tool_tokens += tokens["tool_call_tokens"]
            total_metadata_tokens += tokens["metadata_tokens"]
        
        total_tokens = stats["total_tokens"]
        
        return {
            "total_tokens": total_tokens,
            "distribution": {
                "content": {
                    "tokens": total_content_tokens,
                    "percentage": round((total_content_tokens / total_tokens * 100), 2) if total_tokens > 0 else 0
                },
                "tools": {
                    "tokens": total_tool_tokens,
                    "percentage": round((total_tool_tokens / total_tokens * 100), 2) if total_tokens > 0 else 0
                },
                "metadata": {
                    "tokens": total_metadata_tokens,
                    "percentage": round((total_metadata_tokens / total_tokens * 100), 2) if total_tokens > 0 else 0
                },
                "overhead": {
                    "tokens": total_tokens - total_content_tokens - total_tool_tokens - total_metadata_tokens,
                    "percentage": round(((total_tokens - total_content_tokens - total_tool_tokens - total_metadata_tokens) / total_tokens * 100), 2) if total_tokens > 0 else 0
                }
            },
            "efficiency_score": round((total_content_tokens / total_tokens * 100), 2) if total_tokens > 0 else 0
        }


# 便捷函数
def create_token_counter(model_name: str = "gpt-4") -> TokenCounter:
    """创建Token计数器实例"""
    return TokenCounter(model_name)


def count_message_tokens(message: Message, model_name: str = "gpt-4") -> Dict[str, int]:
    """快速计算单个消息的token数量"""
    counter = TokenCounter(model_name)
    return counter.count_message_tokens(message)


def count_messages_tokens(messages: List[Message], model_name: str = "gpt-4") -> Dict[str, Any]:
    """快速计算消息列表的token数量"""
    counter = TokenCounter(model_name)
    return counter.count_messages_tokens(messages)