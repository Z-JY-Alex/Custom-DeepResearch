"""
集中配置管理模块
从 .env 文件加载配置，提供统一的配置访问接口
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 自动加载项目根目录的 .env 文件
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


def get_llm_config() -> dict:
    """获取主 LLM 配置"""
    return {
        "model_name": os.getenv("DEFAULT_MODEL_NAME", "MaaS_Sonnet_4"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL"),
        "max_tokens": int(os.getenv("DEFAULT_MAX_TOKENS", "32000")),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
        "top_p": float(os.getenv("LLM_TOP_P", "1.0")),
        "timeout": int(os.getenv("LLM_TIMEOUT", "120")),
        "retry_attempts": int(os.getenv("LLM_RETRY_ATTEMPTS", "3")),
    }


def get_compression_llm_config() -> dict:
    """获取 Memory 压缩用的 LLM 配置"""
    return {
        "model_name": os.getenv("COMPRESSION_MODEL_NAME", "MaaS_Sonnet_4"),
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL"),
        "temperature": float(os.getenv("COMPRESSION_TEMPERATURE", "0.3")),
        "max_tokens": int(os.getenv("COMPRESSION_MAX_TOKENS", "1000")),
        "timeout": float(os.getenv("COMPRESSION_TIMEOUT", "30")),
    }


def get_tavily_api_key() -> str:
    """获取 Tavily 搜索 API Key"""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise ValueError("TAVILY_API_KEY 未配置，请在 .env 文件中设置")
    return key


def get_server_config() -> dict:
    """获取服务器配置"""
    return {
        "host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "port": int(os.getenv("SERVER_PORT", "1234")),
    }
