"""
LLM异常模块：定义所有LLM相关的异常类
"""
from typing import Dict, Optional, Any


class LLMException(Exception):
    """LLM异常基类"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = None
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
            "timestamp": self.timestamp
        }
    
    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class RateLimitException(LLMException):
    """速率限制异常"""
    
    def __init__(self, message: str, retry_after: Optional[int] = None, limit_type: str = "requests", **kwargs):
        super().__init__(message, error_code="RATE_LIMIT_EXCEEDED", **kwargs)
        self.retry_after = retry_after  # 建议重试间隔（秒）
        self.limit_type = limit_type    # 限制类型：requests, tokens, etc.
        self.details.update({
            "retry_after": retry_after,
            "limit_type": limit_type
        })
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_after is not None and self.retry_after > 0
    
    def get_retry_delay(self) -> int:
        """获取建议的重试延迟"""
        return self.retry_after or 60  # 默认60秒


class AuthenticationException(LLMException):
    """认证异常"""
    
    def __init__(self, message: str, auth_type: str = "api_key", **kwargs):
        super().__init__(message, error_code="AUTHENTICATION_FAILED", **kwargs)
        self.auth_type = auth_type  # 认证类型：api_key, oauth, etc.
        self.details.update({
            "auth_type": auth_type
        })
    
    def is_recoverable(self) -> bool:
        """检查认证错误是否可恢复"""
        # API密钥错误通常需要人工干预
        return self.auth_type not in ["api_key", "invalid_credentials"]


class ValidationException(LLMException):
    """验证异常"""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Any = None, **kwargs):
        super().__init__(message, error_code="VALIDATION_ERROR", **kwargs)
        self.field = field      # 验证失败的字段
        self.value = value      # 验证失败的值
        self.details.update({
            "field": field,
            "value": str(value) if value is not None else None
        })
    
    def get_field_error(self) -> Optional[str]:
        """获取字段级错误信息"""
        if self.field:
            return f"字段 '{self.field}' 验证失败: {self.message}"
        return None


class ToolException(LLMException):
    """工具调用异常"""
    
    def __init__(self, message: str, tool_name: Optional[str] = None, tool_call_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="TOOL_EXECUTION_ERROR", **kwargs)
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        self.details.update({
            "tool_name": tool_name,
            "tool_call_id": tool_call_id
        })


class ModelNotSupportedException(LLMException):
    """模型不支持异常"""
    
    def __init__(self, message: str, model_name: str, feature: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="MODEL_NOT_SUPPORTED", **kwargs)
        self.model_name = model_name
        self.feature = feature
        self.details.update({
            "model_name": model_name,
            "feature": feature
        })


class TokenLimitException(LLMException):
    """Token限制异常"""
    
    def __init__(self, message: str, current_tokens: int, max_tokens: int, **kwargs):
        super().__init__(message, error_code="TOKEN_LIMIT_EXCEEDED", **kwargs)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens
        self.details.update({
            "current_tokens": current_tokens,
            "max_tokens": max_tokens,
            "overflow": current_tokens - max_tokens
        })
    
    def get_overflow_amount(self) -> int:
        """获取超出的token数量"""
        return max(0, self.current_tokens - self.max_tokens)


class NetworkException(LLMException):
    """网络异常"""
    
    def __init__(self, message: str, status_code: Optional[int] = None, is_timeout: bool = False, **kwargs):
        super().__init__(message, error_code="NETWORK_ERROR", **kwargs)
        self.status_code = status_code
        self.is_timeout = is_timeout
        self.details.update({
            "status_code": status_code,
            "is_timeout": is_timeout
        })
    
    def is_retryable(self) -> bool:
        """检查网络错误是否可重试"""
        if self.is_timeout:
            return True
        if self.status_code:
            # 5xx错误通常可重试，4xx错误通常不可重试
            return 500 <= self.status_code < 600
        return True