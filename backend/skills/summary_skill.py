"""总结技能"""
from typing import AsyncGenerator, Any
from .base import BaseSkill, SkillInfo


class SummarySkill(BaseSkill):
    """总结技能"""

    def __init__(self, **context):
        info = SkillInfo(
            skill_id="summary",
            name="Summary Generation",
            description="Generate comprehensive summaries and reports from various inputs",
            category="reporting",
            complexity="medium",
            required_params=["content"],
            optional_params={"style": "concise", "format": "markdown"},
            can_be_standalone=True,
            compatible_skills=[],
            estimated_time="10-30 seconds",
        )
        super().__init__(info, **context)

    async def execute(self, **kwargs) -> AsyncGenerator[Any, None]:
        yield {"type": "summary_started"}
        yield {"type": "summary_completed", "summary": ""}
