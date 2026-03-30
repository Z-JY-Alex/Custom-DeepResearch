"""
Skills 管理系统

每个 skill 是一个完整的文件夹，包含 SKILL.md 说明文档和相关脚本。
"""

from .manager import SkillManager, Skill, SkillMetadata

__all__ = ["SkillManager", "Skill", "SkillMetadata"]
