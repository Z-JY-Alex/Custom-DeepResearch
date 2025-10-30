import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from enum import Enum
from loguru import logger

from pydantic import BaseModel, Field
from backend.memory.base import BaseMemory
from backend.agent import BaseAgent


class AgentFlowState(str, Enum):
    """AgentFlow状态枚举"""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    

class BaseWorkFlow(BaseModel):
    """Agent流程管理类，支持root_agent和sub_agents之间的调用"""
    
    # 基本属性
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="WorkFlow ID")
    
    # 状态管理
    state: AgentFlowState = Field(default=AgentFlowState.IDLE, description="Flow状态")
    
    # Agent管理
    root_agent: BaseAgent = Field(default=None, description="根Agent")
    sub_agents: Dict[str, BaseAgent] = Field(default_factory=dict, description="子Agent字典")
    
    # 记忆模块
    memory: BaseMemory = Field(default_factory=BaseMemory, description="记忆模块")
    
    # 执行配置
    max_execution_time: float = Field(default=3600.0, description="最大执行时间(秒)")   

    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info(f"AgentFlow {self.workflow_id} 初始化完成")
    
    def get_sub_agent(self, agent_key: str) -> Optional[BaseAgent]:
        """获取子Agent"""
        return self.sub_agents.get(agent_key)
    
    
    def list_sub_agents(self) -> List[str]:
        """列出所有子Agent的键"""
        return list(self.sub_agents.keys())
    
    @abstractmethod
    async def run(self):
        """执行完整的workflow流程, 包括父子agent直接的调用逻辑"""
        
    
