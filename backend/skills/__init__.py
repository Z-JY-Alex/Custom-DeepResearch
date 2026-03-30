"""
SkillManager：技能管理系统

采用延迟加载策略：
1. 初始化时：只读取所有 skill 的 name 和 description (Front Matter)
2. 使用时：按需读取完整 skill 文档
3. 执行时：根据完整说明执行

所有 skills 存储在 backend/skills/ 下，每个文件格式为：
---
name: skill_name
description: brief description
---
# Full content...
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger


class SkillMetadata:
    """Skill 的元数据（name 和 description）"""

    def __init__(self, skill_id: str, name: str, description: str, file_path: Path):
        self.skill_id = skill_id  # 文件名（不含扩展名）
        self.name = name
        self.description = description
        self.file_path = file_path

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
        }


class Skill:
    """完整的 Skill（包含全部内容）"""

    def __init__(
        self,
        skill_id: str,
        name: str,
        description: str,
        content: str,
        file_path: Path,
    ):
        self.skill_id = skill_id
        self.name = name
        self.description = description
        self.content = content  # 完整的 Markdown 内容
        self.file_path = file_path

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "file_path": str(self.file_path),
        }


class SkillManager:
    """技能管理器

    1. 初始化时只加载 skill 元数据
    2. 按需延迟加载完整 skill 内容
    """

    def __init__(self, skills_dir: Optional[str] = None):
        """
        初始化 SkillManager

        Args:
            skills_dir: Skills 目录路径（默认为 backend/skills）
        """
        if skills_dir is None:
            # 默认指向当前目录（backend/skills）
            skills_dir = Path(__file__).parent

        self.skills_dir = Path(skills_dir)

        # 验证目录存在
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            self.skills_dir.mkdir(parents=True, exist_ok=True)

        # 元数据缓存（初始加载）
        self._metadata: Dict[str, SkillMetadata] = {}

        # 完整 skill 缓存（延迟加载）
        self._skills: Dict[str, Skill] = {}

        # 初始化时加载所有元数据
        self._load_metadata()

    def _load_metadata(self) -> None:
        """加载所有 skill 的元数据（name 和 description）"""
        logger.info(f"Loading skill metadata from: {self.skills_dir}")

        md_files = sorted(self.skills_dir.glob("*.md"))

        for file_path in md_files:
            try:
                skill_id = file_path.stem  # 文件名不含扩展名
                metadata = self._extract_metadata(file_path)

                if metadata:
                    self._metadata[skill_id] = metadata
                    logger.info(
                        f"Loaded skill metadata: {skill_id} - {metadata.name}"
                    )
            except Exception as e:
                logger.error(f"Error loading skill from {file_path}: {e}")

    def _extract_metadata(self, file_path: Path) -> Optional[SkillMetadata]:
        """从 skill 文件提取元数据（Front Matter）"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 解析 Front Matter (---...---)
            if not content.startswith("---"):
                logger.warning(f"Skill file {file_path} does not start with ---")
                return None

            parts = content.split("---", 2)
            if len(parts) < 2:
                logger.warning(f"Skill file {file_path} has no valid Front Matter")
                return None

            front_matter = parts[1].strip()
            metadata = yaml.safe_load(front_matter)

            if not metadata or "name" not in metadata:
                logger.warning(f"Skill file {file_path} missing 'name' in Front Matter")
                return None

            return SkillMetadata(
                skill_id=file_path.stem,
                name=metadata.get("name", "Untitled"),
                description=metadata.get("description", "No description"),
                file_path=file_path,
            )

        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {e}")
            return None

    def list_skills(self) -> List[Dict[str, Any]]:
        """获取所有 skills 的元数据列表

        Returns:
            包含 skill_id, name, description 的列表
        """
        return [meta.to_dict() for meta in self._metadata.values()]

    def get_skill_metadata(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 skill 的元数据

        Args:
            skill_id: Skill ID（文件名不含扩展名）

        Returns:
            Skill 的元数据字典，或 None 如果不存在
        """
        if skill_id not in self._metadata:
            logger.warning(f"Skill metadata not found: {skill_id}")
            return None

        return self._metadata[skill_id].to_dict()

    def has_skill(self, skill_id: str) -> bool:
        """检查是否存在指定的 skill"""
        return skill_id in self._metadata

    def load_skill(self, skill_id: str) -> Optional[Skill]:
        """延迟加载完整的 skill 内容

        Args:
            skill_id: Skill ID

        Returns:
            完整的 Skill 对象，或 None 如果不存在
        """
        # 检查缓存
        if skill_id in self._skills:
            return self._skills[skill_id]

        # 检查元数据是否存在
        if skill_id not in self._metadata:
            logger.warning(f"Skill not found: {skill_id}")
            return None

        try:
            metadata = self._metadata[skill_id]
            file_path = metadata.file_path

            # 读取完整内容
            with open(file_path, "r", encoding="utf-8") as f:
                full_content = f.read()

            # 分离 Front Matter 和内容
            parts = full_content.split("---", 2)
            content_md = parts[2].strip() if len(parts) > 2 else ""

            skill = Skill(
                skill_id=skill_id,
                name=metadata.name,
                description=metadata.description,
                content=content_md,
                file_path=file_path,
            )

            # 缓存
            self._skills[skill_id] = skill

            logger.info(f"Loaded full skill content: {skill_id}")
            return skill

        except Exception as e:
            logger.error(f"Error loading full skill content for {skill_id}: {e}")
            return None

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """获取完整的 skill 对象

        Args:
            skill_id: Skill ID

        Returns:
            Skill 对象，或 None 如果不存在
        """
        return self.load_skill(skill_id)

    def get_skill_content(self, skill_id: str) -> Optional[str]:
        """获取 skill 的完整内容（Markdown）

        Args:
            skill_id: Skill ID

        Returns:
            Skill 的完整 Markdown 内容，或 None 如果不存在
        """
        skill = self.load_skill(skill_id)
        if not skill:
            return None

        return skill.content

    def search_skills_by_name(self, keyword: str) -> List[Dict[str, Any]]:
        """按名称搜索 skills

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的 skills 元数据列表
        """
        results = []
        keyword_lower = keyword.lower()

        for meta in self._metadata.values():
            if keyword_lower in meta.name.lower():
                results.append(meta.to_dict())

        return results

    def search_skills_by_description(self, keyword: str) -> List[Dict[str, Any]]:
        """按描述搜索 skills

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的 skills 元数据列表
        """
        results = []
        keyword_lower = keyword.lower()

        for meta in self._metadata.values():
            if keyword_lower in meta.description.lower():
                results.append(meta.to_dict())

        return results

    def get_skills_summary(self) -> Dict[str, Any]:
        """获取 skills 系统的摘要

        Returns:
            包含总数、名称列表等的摘要信息
        """
        return {
            "total_count": len(self._metadata),
            "skills": [
                {"skill_id": meta.skill_id, "name": meta.name}
                for meta in self._metadata.values()
            ],
            "loaded_count": len(self._skills),
        }
