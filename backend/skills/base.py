"""
Skill 基类和数据模型
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List, AsyncGenerator
from pydantic import BaseModel, Field
from datetime import datetime


class SkillStatus(str, Enum):
    """Skill 执行状态"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SkillInfo(BaseModel):
    """Skill 的信息描述"""
    skill_id: str                           # 唯一标识
    name: str                               # 技能名称
    description: str                        # 技能描述
    category: str                           # 分类（search, code, analysis, etc）
    complexity: str                         # 复杂度（simple, medium, complex）
    required_params: List[str]              # 必需参数
    optional_params: Dict[str, Any]         # 可选参数及默认值
    can_be_standalone: bool = True          # 是否可以独立执行
    requires_planning: bool = False         # 是否需要先规划
    compatible_skills: List[str] = []       # 兼容的 skills（可以组合的）
    estimated_time: str = "unknown"         # 预计执行时间

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典供外部使用"""
        return self.model_dump()


class SkillResult(BaseModel):
    """Skill 执行结果"""
    skill_id: str
    status: SkillStatus
    result: Optional[str] = None            # 执行结果内容
    output: Optional[Any] = None            # 结构化输出
    error: Optional[str] = None             # 错误信息
    execution_time: float = 0.0             # 执行耗时（秒）
    artifacts: Dict[str, Any] = {}          # 生成的产物
    metadata: Dict[str, Any] = {}           # 额外元数据


class BaseSkill(ABC):
    """所有 Skill 的基类"""

    def __init__(self, skill_info: SkillInfo, **kwargs):
        """
        初始化 Skill

        Args:
            skill_info: Skill 的信息描述
            **kwargs: 依赖注入（如 llm_config, artifact_manager 等）
        """
        self.info = skill_info
        self.status = SkillStatus.IDLE
        self.context = kwargs

    @property
    def skill_id(self) -> str:
        return self.info.skill_id

    @property
    def name(self) -> str:
        return self.info.name

    def describe(self) -> Dict[str, Any]:
        """
        获取 Skill 的详细描述

        Returns:
            包含 name, description, parameters 等的字典
        """
        return {
            "skill_id": self.info.skill_id,
            "name": self.info.name,
            "description": self.info.description,
            "category": self.info.category,
            "complexity": self.info.complexity,
            "required_params": self.info.required_params,
            "optional_params": self.info.optional_params,
            "can_be_standalone": self.info.can_be_standalone,
            "requires_planning": self.info.requires_planning,
            "compatible_skills": self.info.compatible_skills,
            "estimated_time": self.info.estimated_time,
        }

    @abstractmethod
    async def execute(self, **kwargs) -> AsyncGenerator[Any, None]:
        """
        执行 Skill

        这是一个异步生成器，支持流式输出

        Args:
            **kwargs: 执行参数

        Yields:
            执行过程中的事件或结果块
        """
        pass

    async def validate_params(self, **kwargs) -> tuple[bool, Optional[str]]:
        """
        验证执行参数

        Returns:
            (是否有效, 错误信息)
        """
        # 检查必需参数
        for param in self.info.required_params:
            if param not in kwargs:
                return False, f"Missing required parameter: {param}"
        return True, None

    def get_compatible_skills(self) -> List[str]:
        """获取与此 Skill 兼容的其他 Skill"""
        return self.info.compatible_skills

    def can_combine_with(self, other_skill_id: str) -> bool:
        """检查是否可以与另一个 Skill 组合"""
        return other_skill_id in self.info.compatible_skills
