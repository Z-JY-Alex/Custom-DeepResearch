"""
历史记录保存和读取工具模块
用于保存和恢复Agent的对话历史记录
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger

from backend.llm.base import Message, MessageRole
from backend.tools.base import ToolCall


def save_history_to_file(
    agent_id: str,
    agent_name: str,
    task: str,
    all_history: List[Message],
    filepath: Optional[str] = None,
    workdir: str = "/data/zhujingyuan/deepresearch"
) -> str:
    """
    保存 all_history 到文件
    
    Args:
        agent_id: Agent ID
        agent_name: Agent名称
        task: 任务描述
        all_history: 消息历史列表
        filepath: 文件路径，如果为None则使用默认路径
        workdir: 工作目录
        
    Returns:
        str: 保存的文件路径
    """
    if filepath is None:
        # 创建基于agent_id和时间戳的默认文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"history_{agent_id}.json"
        filepath = os.path.join(workdir, "output", "history", filename)
    
    # 确保目录存在
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    try:
        # 将 Message 对象转换为可序列化的字典
        serializable_history = []
        for msg in all_history:
            # 如果不是 Pydantic 模型，尝试转换为字典
            msg_dict = {
                "role": msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                "content": msg.content,
                "timestamp": msg.timestamp,
                "metadata": msg.metadata,
                "tool_calls": [tc.model_dump() if hasattr(tc, 'model_dump') else tc for tc in msg.tool_calls] if msg.tool_calls else None,
                "tool_call_id": msg.tool_call_id
            }
            serializable_history.append(msg_dict)
        
        # 保存数据
        save_data = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "task": task,
            "save_timestamp": datetime.now().isoformat(),
            "total_messages": len(serializable_history),
            "history": serializable_history
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"历史记录已保存到: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"保存历史记录失败: {e}")
        raise


def load_history_to_messages(filepath: str) -> List[Message]:
    """
    从文件读取历史记录并还原为Message对象列表
    
    Args:
        filepath: 文件路径
        
    Returns:
        List[Message]: Message对象列表，与原始all_history格式相同
    """
    try:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"历史文件不存在: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 还原Message对象列表
        messages = []
        for msg_dict in data.get('history', []):
            # 还原MessageRole枚举
            role_str = msg_dict.get('role')
            if role_str == 'system':
                role = MessageRole.SYSTEM
            elif role_str == 'user':
                role = MessageRole.USER
            elif role_str == 'assistant':
                role = MessageRole.ASSISTANT
            elif role_str == 'tool':
                role = MessageRole.TOOL
            else:
                role = MessageRole.USER  # 默认值
            
            # 还原tool_calls
            tool_calls = None
            if msg_dict.get('tool_calls'):
                # 这里简单处理，保持原始数据结构
                # 如果需要完整还原ToolCall对象，需要根据具体的ToolCall类来处理
                tool_calls = msg_dict['tool_calls']
            
            # 创建Message对象
            message = Message(
                role=role,
                content=msg_dict.get('content', ''),
                timestamp=msg_dict.get('timestamp'),
                metadata=msg_dict.get('metadata'),
                tool_calls=tool_calls,
                tool_call_id=msg_dict.get('tool_call_id')
            )
            messages.append(message)
        
        logger.info(f"成功加载历史记录: {filepath}")
        logger.info(f"Agent: {data.get('agent_name', 'Unknown')} ({data.get('agent_id', 'Unknown')})")
        logger.info(f"任务: {data.get('task', 'Unknown')}")  
        logger.info(f"消息数量: {len(messages)}")
        logger.info(f"保存时间: {data.get('save_timestamp', 'Unknown')}")
        
        return messages
        
    except Exception as e:
        logger.error(f"加载历史记录失败: {e}")
        raise


def load_history_info(filepath: str) -> Dict[str, Any]:
    """
    从文件读取历史记录的基本信息（不包含详细消息内容）
    
    Args:
        filepath: 文件路径
        
    Returns:
        Dict[str, Any]: 包含基本信息的字典
    """
    try:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"历史文件不存在: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 只返回基本信息，不包含详细的history内容
        info = {
            "agent_id": data.get('agent_id', 'Unknown'),
            "agent_name": data.get('agent_name', 'Unknown'),
            "task": data.get('task', 'Unknown'),
            "save_timestamp": data.get('save_timestamp', 'Unknown'),
            "total_messages": data.get('total_messages', 0),
            "filepath": filepath
        }
        
        return info
        
    except Exception as e:
        logger.error(f"读取历史信息失败: {e}")
        raise


def list_history_files(history_dir: str = None, workdir: str = "/data/zhujingyuan/deepresearch") -> List[Dict[str, Any]]:
    """
    列出历史文件夹中的所有历史文件
    
    Args:
        history_dir: 历史文件夹路径，如果为None则使用默认路径
        workdir: 工作目录
        
    Returns:
        List[Dict[str, Any]]: 历史文件信息列表
    """
    if history_dir is None:
        history_dir = os.path.join(workdir, "output", "history")
    
    if not os.path.exists(history_dir):
        logger.warning(f"历史文件夹不存在: {history_dir}")
        return []
    
    history_files = []
    try:
        for filename in os.listdir(history_dir):
            if filename.endswith('.json') and filename.startswith('history_'):
                filepath = os.path.join(history_dir, filename)
                try:
                    info = load_history_info(filepath)
                    history_files.append(info)
                except Exception as e:
                    logger.warning(f"无法读取历史文件 {filename}: {e}")
        
        # 按保存时间排序
        history_files.sort(key=lambda x: x.get('save_timestamp', ''), reverse=True)
        
    except Exception as e:
        logger.error(f"列出历史文件失败: {e}")
        
    return history_files