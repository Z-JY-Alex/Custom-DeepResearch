"""
SkillManager：技能管理器

统一管理所有 skills，提供：
- 列出所有可用 skills
- 获取 skill 详情
- 验证 skill 参数
- 执行 skill
"""

from typing import Dict, List, Optional, Any, AsyncGenerator
from loguru import logger
from .base import BaseSkill, SkillInfo, SkillStatus, SkillResult
from .web_search_skill import WebSearchSkill
from .code_analysis_skill import CodeAnalysisSkill
from .content_analysis_skill import ContentAnalysisSkill
from .test_generation_skill import TestGenerationSkill
from .code_generation_skill import CodeGenerationSkill
from .data_analysis_skill import DataAnalysisSkill
from .summary_skill import SummarySkill


class SkillManager:
    """技能管理器：管理所有可用的 skills"""

    def __init__(self, **context):
        """
        初始化 SkillManager

        Args:
            **context: 上下文信息（llm_config, artifact_manager, memory, session_id 等）
        """
        self.context = context
        self._skills: Dict[str, BaseSkill] = {}
        self._initialize_skills()

    def _initialize_skills(self):
        """初始化所有内置 skills"""
        skills_config = [
            WebSearchSkill(**self.context),
            CodeAnalysisSkill(**self.context),
            ContentAnalysisSkill(**self.context),
            TestGenerationSkill(**self.context),
            CodeGenerationSkill(**self.context),
            DataAnalysisSkill(**self.context),
            SummarySkill(**self.context),
        ]

        for skill in skills_config:
            self._skills[skill.skill_id] = skill
            logger.info(f"Initialized skill: {skill.name}")

    def list_skills(self) -> List[Dict[str, Any]]:
        """
        获取所有 skills 的摘要列表

        Returns:
            包含所有 skills 的简要信息列表
        """
        return [
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "category": skill.info.category,
                "complexity": skill.info.complexity,
                "can_be_standalone": skill.info.can_be_standalone,
            }
            for skill in self._skills.values()
        ]

    def get_skill_details(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 skill 的详细信息

        Args:
            skill_id: Skill ID

        Returns:
            Skill 的详细描述，或 None 如果不存在
        """
        skill = self._skills.get(skill_id)
        if not skill:
            logger.warning(f"Skill not found: {skill_id}")
            return None

        return skill.describe()

    def get_skill(self, skill_id: str) -> Optional[BaseSkill]:
        """
        获取 skill 实例

        Args:
            skill_id: Skill ID

        Returns:
            Skill 实例，或 None 如果不存在
        """
        return self._skills.get(skill_id)

    def has_skill(self, skill_id: str) -> bool:
        """检查是否有指定的 skill"""
        return skill_id in self._skills

    async def can_execute(self, skill_id: str, **params) -> tuple[bool, Optional[str]]:
        """
        检查是否可以执行 skill

        Args:
            skill_id: Skill ID
            **params: 执行参数

        Returns:
            (是否可以执行, 错误信息)
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return False, f"Skill not found: {skill_id}"

        # 检查参数
        valid, error = await skill.validate_params(**params)
        if not valid:
            return False, error

        return True, None

    async def execute_skill(
        self, skill_id: str, **params
    ) -> AsyncGenerator[Any, None]:
        """
        执行 skill

        Args:
            skill_id: Skill ID
            **params: 执行参数

        Yields:
            执行过程中的事件或结果块

        Raises:
            ValueError: 如果 skill 不存在或参数无效
        """
        skill = self.get_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")

        # 验证参数
        valid, error = await skill.validate_params(**params)
        if not valid:
            raise ValueError(f"Invalid parameters: {error}")

        logger.info(f"Executing skill: {skill.name} with params: {params}")

        try:
            skill.status = SkillStatus.RUNNING

            async for chunk in skill.execute(**params):
                yield chunk

            skill.status = SkillStatus.SUCCESS

        except Exception as e:
            skill.status = SkillStatus.FAILED
            logger.error(f"Skill execution failed: {skill.name}, error: {str(e)}")
            raise

    def get_compatible_skills(self, skill_id: str) -> List[str]:
        """
        获取与指定 skill 兼容的其他 skills

        Args:
            skill_id: Skill ID

        Returns:
            兼容 skill 的 ID 列表
        """
        skill = self.get_skill(skill_id)
        if not skill:
            return []

        return skill.get_compatible_skills()

    def suggest_next_skills(self, current_skill_id: str) -> List[Dict[str, Any]]:
        """
        建议执行完当前 skill 后可以执行的 skills

        Args:
            current_skill_id: 当前 Skill ID

        Returns:
            建议的 skills 列表
        """
        compatible = self.get_compatible_skills(current_skill_id)
        return [
            {
                "skill_id": skill_id,
                "name": self.get_skill(skill_id).name,
                "description": self.get_skill(skill_id).info.description,
            }
            for skill_id in compatible
            if self.has_skill(skill_id)
        ]

    def get_skills_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        按分类获取 skills

        Args:
            category: 分类名称

        Returns:
            匹配的 skills 列表
        """
        return [
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "description": skill.info.description,
            }
            for skill in self._skills.values()
            if skill.info.category == category
        ]

    def get_simple_skills(self) -> List[Dict[str, Any]]:
        """获取所有可以独立执行的简单 skills"""
        return [
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "complexity": skill.info.complexity,
            }
            for skill in self._skills.values()
            if skill.info.can_be_standalone and skill.info.complexity != "complex"
        ]

    def get_complex_skills(self) -> List[Dict[str, Any]]:
        """获取需要规划的复杂 skills"""
        return [
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "requires_planning": skill.info.requires_planning,
            }
            for skill in self._skills.values()
            if skill.info.requires_planning or skill.info.complexity == "complex"
        ]

    def register_skill(self, skill: BaseSkill) -> None:
        """
        注册自定义 skill

        Args:
            skill: 要注册的 Skill 实例
        """
        self._skills[skill.skill_id] = skill
        logger.info(f"Registered custom skill: {skill.name}")
