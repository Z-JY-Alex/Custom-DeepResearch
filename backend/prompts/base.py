from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from backend.agent.schema import AgentTypes
from backend.tools.base import BaseTool, ToolFunction


class BasePrompt(BaseModel, ABC):
    """Prompt 基类"""
    
    # Prompt 角色
    role: str = Field(default="智能助手", description="Prompt 角色")
    
    # 用户画像
    user_profile: Optional[Dict[str, Any]] = Field(default=None, description="用户画像信息")
    
    # 计划信息
    plan_info: Optional[str] = Field(default=None, description="计划信息")
    
    # 当前任务描述
    current_task_description: Optional[str] = Field(default=None, description="当前任务描述")
    
    # 当前任务目标
    current_task_objectives: Optional[List[str]] = Field(default=None, description="当前任务目标")
    
    # 上下文信息
    context_info: Dict[str, Any] = Field(default_factory=dict, description="上下文信息")
    
    # 输出格式
    output_format: Optional[str] = Field(default=None, description="期望的输出格式")
    

    class Config:
        arbitrary_types_allowed = True

    def generate_prompt(self) -> str:
        """生成 prompt 文本"""
        prompt_parts = []
        
        # 角色信息
        if self.role:
            prompt_parts.append(f"<🎭 角色定义>\n你是一个{self.role}。\n</🎭 角色定义>")
        
        # 用户画像
        if self.user_profile:
            profile_text = "\n".join([f"- {k}: {v}" for k, v in self.user_profile.items()])
            prompt_parts.append(f"\n\n<👤 用户画像>\n{profile_text}\n</👤 用户画像>")
        
        # 上下文信息
        if self.context_info:
            context_text = "\n".join([f"- {k}: {v}" for k, v in self.context_info.items()])
            prompt_parts.append(f"\n\n<📋 上下文信息>\n{context_text}\n</📋 上下文信息>")
        
        # 计划信息
        if self.plan_info:
            prompt_parts.append(f"\n\n<📅 计划信息>\n{self.plan_info}\n</📅 计划信息>")
        
        # 当前任务描述
        if self.current_task_description:
            prompt_parts.append(f"\n\n<🎯 当前任务>\n{self.current_task_description}\n</🎯 当前任务>")
        
        # 当前任务目标
        if self.current_task_objectives:
            objectives_text = "\n".join([f"- {obj}" for obj in self.current_task_objectives])
            prompt_parts.append(f"\n\n<🏆 任务目标>\n{objectives_text}\n</🏆 任务目标>")
        
        # 工具列表
        if self.tools:
            tools_text = "\n".join([f"- {tool.name}: {tool.description}" for tool in self.tools])
            prompt_parts.append(f"\n\n<🛠️ 可用工具>\n{tools_text}\n</🛠️ 可用工具>")
        
        # 输出格式
        if self.output_format:
            prompt_parts.append(f"\n\n<📝 输出格式>\n{self.output_format}\n</📝 输出格式>")
        
        return "".join(prompt_parts)
    

    def add_tool(self, tool: Union[BaseTool, ToolFunction]) -> None:
        """添加工具"""
        if tool not in self.tools:
            self.tools.append(tool)

    def remove_tool(self, tool_name: str) -> bool:
        """移除工具"""
        for i, tool in enumerate(self.tools):
            if tool.name == tool_name:
                self.tools.pop(i)
                return True
        return False

    def get_tool_by_name(self, tool_name: str) -> Optional[Union[BaseTool, ToolFunction]]:
        """根据名称获取工具"""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None