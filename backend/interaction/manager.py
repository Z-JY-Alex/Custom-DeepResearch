"""
用户交互管理器
处理AI与用户之间的异步交互，支持问答、超时处理等功能
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from loguru import logger
from pydantic import BaseModel, Field


class InteractionData(BaseModel):
    """交互数据模型"""
    interaction_id: str = Field(..., description="交互ID")
    session_id: str = Field(..., description="会话ID")
    question: str = Field(..., description="问题内容")
    question_type: str = Field(default="text", description="问题类型")
    options: list = Field(default_factory=list, description="选择项")
    timeout: int = Field(default=300, description="超时时间（秒）")
    required: bool = Field(default=True, description="是否必须回答")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    answered_at: Optional[datetime] = Field(default=None, description="回答时间")
    answer: Optional[str] = Field(default=None, description="用户回答")
    status: str = Field(default="pending", description="状态：pending/answered/timeout/cancelled")


class InteractionManager:
    """用户交互管理器"""
    
    def __init__(self):
        # 存储待处理的交互
        self.pending_interactions: Dict[str, asyncio.Future] = {}
        # 存储交互数据
        self.interaction_data: Dict[str, InteractionData] = {}
        # 存储超时任务
        self.timeout_tasks: Dict[str, asyncio.Task] = {}
        # 会话到交互的映射
        self.session_interactions: Dict[str, list] = {}
    
    async def create_interaction(
        self, 
        session_id: str,
        question: str,
        question_type: str = "text",
        options: list = None,
        timeout: int = 300,
        required: bool = True
    ) -> tuple[str, asyncio.Future]:
        """
        创建新的用户交互
        
        Args:
            session_id: 会话ID
            question: 问题内容
            question_type: 问题类型 (text/choice/confirm)
            options: 选择项列表
            timeout: 超时时间（秒）
            required: 是否必须回答
            
        Returns:
            tuple: (interaction_id, future)
        """
        interaction_id = str(uuid.uuid4())
        
        # 创建交互数据
        interaction_data = InteractionData(
            interaction_id=interaction_id,
            session_id=session_id,
            question=question,
            question_type=question_type,
            options=options or [],
            timeout=timeout,
            required=required
        )
        
        # 创建Future用于等待回答
        future = asyncio.Future()
        
        # 存储数据
        self.pending_interactions[interaction_id] = future
        self.interaction_data[interaction_id] = interaction_data
        
        # 添加到会话映射
        if session_id not in self.session_interactions:
            self.session_interactions[session_id] = []
        self.session_interactions[session_id].append(interaction_id)
        
        # 设置超时任务
        timeout_task = asyncio.create_task(
            self._handle_timeout(interaction_id, timeout)
        )
        self.timeout_tasks[interaction_id] = timeout_task
        
        logger.info(f"创建用户交互: {interaction_id}, 会话: {session_id}, 问题: {question[:50]}...")
        
        return interaction_id, future
    
    async def submit_answer(self, interaction_id: str, answer: str) -> bool:
        """
        提交用户回答
        
        Args:
            interaction_id: 交互ID
            answer: 用户回答
            
        Returns:
            bool: 是否提交成功
        """
        if interaction_id not in self.pending_interactions:
            logger.warning(f"交互不存在或已过期: {interaction_id}")
            return False
        
        future = self.pending_interactions[interaction_id]
        interaction_data = self.interaction_data[interaction_id]
        
        if future.done():
            logger.warning(f"交互已完成: {interaction_id}")
            return False
        
        # 验证回答格式
        if not self._validate_answer(interaction_data, answer):
            logger.warning(f"回答格式无效: {interaction_id}, 回答: {answer}")
            return False
        
        # 更新交互数据
        interaction_data.answer = answer
        interaction_data.answered_at = datetime.now()
        interaction_data.status = "answered"
        
        # 设置Future结果
        future.set_result(answer)
        
        # 清理资源
        self._cleanup_interaction(interaction_id)
        
        logger.info(f"收到用户回答: {interaction_id}, 回答: {answer}")
        return True
    
    async def cancel_interaction(self, interaction_id: str, reason: str = "cancelled") -> bool:
        """
        取消交互
        
        Args:
            interaction_id: 交互ID
            reason: 取消原因
            
        Returns:
            bool: 是否取消成功
        """
        if interaction_id not in self.pending_interactions:
            return False
        
        future = self.pending_interactions[interaction_id]
        interaction_data = self.interaction_data[interaction_id]
        
        if not future.done():
            interaction_data.status = reason
            future.cancel()
        
        self._cleanup_interaction(interaction_id)
        logger.info(f"交互已取消: {interaction_id}, 原因: {reason}")
        return True
    
    async def get_interaction_data(self, interaction_id: str) -> Optional[InteractionData]:
        """获取交互数据"""
        return self.interaction_data.get(interaction_id)
    
    async def get_session_interactions(self, session_id: str) -> list[InteractionData]:
        """获取会话的所有交互"""
        if session_id not in self.session_interactions:
            return []
        
        interactions = []
        for interaction_id in self.session_interactions[session_id]:
            if interaction_id in self.interaction_data:
                interactions.append(self.interaction_data[interaction_id])
        
        return interactions
    
    async def cleanup_session(self, session_id: str):
        """清理会话的所有交互"""
        if session_id not in self.session_interactions:
            return
        
        interaction_ids = self.session_interactions[session_id].copy()
        for interaction_id in interaction_ids:
            await self.cancel_interaction(interaction_id, "session_cleanup")
        
        del self.session_interactions[session_id]
        logger.info(f"会话交互已清理: {session_id}")
    
    def _validate_answer(self, interaction_data: InteractionData, answer: str) -> bool:
        """验证用户回答格式"""
        if not answer or not answer.strip():
            return False
        
        # 选择题验证
        if interaction_data.question_type == "choice":
            return answer in interaction_data.options
        
        # 确认题验证
        if interaction_data.question_type == "confirm":
            return answer.lower() in ["yes", "no", "y", "n", "是", "否", "true", "false"]
        
        # 文本题验证（基本长度检查）
        if interaction_data.question_type == "text":
            return len(answer.strip()) >= 1
        
        return True
    
    async def _handle_timeout(self, interaction_id: str, timeout: int):
        """处理交互超时"""
        try:
            await asyncio.sleep(timeout)
            
            if interaction_id in self.pending_interactions:
                future = self.pending_interactions[interaction_id]
                interaction_data = self.interaction_data[interaction_id]
                
                if not future.done():
                    interaction_data.status = "timeout"
                    
                    if interaction_data.required:
                        future.set_exception(TimeoutError(f"用户交互超时: {timeout}秒"))
                    else:
                        # 非必须回答，返回默认值
                        default_answer = self._get_default_answer(interaction_data)
                        future.set_result(default_answer)
                    
                    logger.warning(f"交互超时: {interaction_id}, 超时时间: {timeout}秒")
                
                self._cleanup_interaction(interaction_id)
                
        except asyncio.CancelledError:
            # 超时任务被取消（正常情况）
            pass
        except Exception as e:
            logger.error(f"处理交互超时时出错: {interaction_id}, 错误: {e}")
    
    def _get_default_answer(self, interaction_data: InteractionData) -> str:
        """获取默认回答"""
        if interaction_data.question_type == "choice" and interaction_data.options:
            return interaction_data.options[0]  # 返回第一个选项
        elif interaction_data.question_type == "confirm":
            return "no"  # 默认否定
        else:
            return "跳过"  # 文本题默认跳过
    
    def _cleanup_interaction(self, interaction_id: str):
        """清理交互资源"""
        # 取消超时任务
        if interaction_id in self.timeout_tasks:
            timeout_task = self.timeout_tasks[interaction_id]
            if not timeout_task.done():
                timeout_task.cancel()
            del self.timeout_tasks[interaction_id]
        
        # 清理pending交互
        if interaction_id in self.pending_interactions:
            del self.pending_interactions[interaction_id]
        
        # 注意：保留interaction_data用于历史记录
    
    def get_stats(self) -> Dict[str, Any]:
        """获取交互统计信息"""
        total_interactions = len(self.interaction_data)
        pending_count = len(self.pending_interactions)
        
        status_counts = {}
        for data in self.interaction_data.values():
            status = data.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_interactions": total_interactions,
            "pending_interactions": pending_count,
            "active_sessions": len(self.session_interactions),
            "status_distribution": status_counts,
            "created_at": datetime.now().isoformat()
        }


# 全局交互管理器实例
interaction_manager = InteractionManager()
