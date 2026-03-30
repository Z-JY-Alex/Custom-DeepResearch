"""
Skills 管理模块：提供高级功能接口

Skills 是比 Tools 更高层的抽象，代表完整的功能块
主 Agent 通过 SkillManager 访问所有可用的 skills
"""

from .manager import SkillManager
from .base import BaseSkill, SkillInfo, SkillStatus

__all__ = [
    "SkillManager",
    "BaseSkill",
    "SkillInfo",
    "SkillStatus",
]
