
"""
Artifact管理器 - 负责工件的创建和显示
简化版本，只保留核心功能
"""
import os
import asyncio
import hashlib
import mimetypes
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, BinaryIO
from pathlib import Path
from uuid import uuid4

from .schema import ArtifactSchema, ArtifactType, ArtifactFileSize
from backend.llm import BaseLLM, Message, MessageRole


class ArtifactManager:
    """
    工件管理器类 - 简化版本
    
    提供工件的基础功能：
    - 创建工件
    - 显示工件
    
    所有数据存储在本地文件系统中：
    - 工件内容存储在 {storage_path} 目录
    """
    
    def __init__(
        self, 
        session_id: str,
        llm: Optional[BaseLLM] = None,
        storage_path: str = "./output/artifacts_storage"
    ):
        """
        初始化ArtifactManager
        
        Args:
            llm: LLM实例，用于生成摘要
            storage_path: 工件存储根路径
        """
        self.session_id = session_id
        self.llm = llm
        if self.session_id:
            self.storage_path = Path(f"{self.session_id}/artifacts_storage")
        else:
            self.storage_path = Path(storage_path)
        self.artifacts_content = []
        self._lock = asyncio.Lock()  # 并发写入安全锁
        
        self._init_storage()
    
    def _init_storage(self) -> None:
        """初始化存储目录和索引文件"""
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def _determine_file_size(self, size_bytes: int) -> ArtifactFileSize:
        """
        根据字节大小确定文件大小类别
        
        Args:
            size_bytes: 文件大小（字节）
            
        Returns:
            ArtifactFileSize: 文件大小枚举值
        """
        mb = 1024 * 1024
        if size_bytes < mb:
            return ArtifactFileSize.SMALL
        elif size_bytes < 10 * mb:
            return ArtifactFileSize.MEDIUM
        else:
            return ArtifactFileSize.LARGE
    
    def _generate_artifact_id(self, content: Union[str, bytes] = None) -> str:
        """
        生成唯一的工件ID
        
        Args:
            content: 工件内容，用于生成哈希
            
        Returns:
            str: 工件ID
        """
        if content:
            if isinstance(content, str):
                content = content.encode('utf-8')
            content_hash = hashlib.md5(content).hexdigest()[:8]
            return f"artifact_{content_hash}_{uuid4().hex[:8]}"
        else:
            return f"artifact_{uuid4().hex}"
    
    async def generate_summary(self, content: Union[str, bytes], artifact_type: ArtifactType) -> Optional[str]:
        """
        生成工件摘要
        
        Args:
            content: 工件内容
            artifact_type: 工件类型
            
        Returns:
            Optional[str]: 生成的摘要，如果无法生成则返回None
        """
        if not self.llm:
            return None
        
        # 只为文本类型生成摘要
        if artifact_type != ArtifactType.TEXT:
            return None
        
        try:
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='ignore')
            
            # 限制内容长度避免过长
            if len(content) > 5000:
                content = content[:5000] + "..."
            
            prompt = f"请为以下内容生成简洁的摘要（不超过200字）：\n\n{content}"
            messages = [Message(role=MessageRole.USER, content=prompt)]
            
            response = await self.llm.generate(messages)
            return response.strip() if response else None
            
        except Exception as e:
            print(f"生成摘要时出错: {e}")
            return None

    async def create_artifact(
        self,
        content: Union[str, bytes, BinaryIO],
        summary: Optional[str] = None,
        artifact_type: Optional[ArtifactType] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        file_path: Optional[str] = None
    ) -> ArtifactSchema:
        """
        创建新的工件
        
        Args:
            content: 工件内容
            artifact_type: 工件类型，如果不提供则自动推断
            metadata: 元数据字典
            tags: 标签列表
            file_path: 原始文件路径（用于推断类型）
            generate_summary: 是否生成摘要
            
        Returns:
            ArtifactSchema: 创建的工件对象
        """
        # 处理内容
        if hasattr(content, 'read'):  # 如果是文件对象
            content = content.read()
        
        # 生成工件ID
        artifact_id = self._generate_artifact_id(content)
                
        # 确定文件大小
        if isinstance(content, str):
            size_bytes = len(content.encode('utf-8'))
        else:
            size_bytes = len(content)
            
        file_size = self._determine_file_size(size_bytes)
        
        # # 生成摘要
        # summary = None
        # if generate_summary:
        #     summary = await self.generate_summary(content, artifact_type)
        
        # 创建工件对象
        now = datetime.now().isoformat()
        artifact = ArtifactSchema(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            metadata=metadata or {},
            summary=summary,
            content=content if artifact_type == ArtifactType.TEXT and len(str(content)) < 1000 else None,
            content_location=file_path,
            created_at=now,
            updated_at=now,
            tags=tags or [],
            file_size=file_size
        )
        
        async with self._lock:
            self.artifacts_content.append(artifact)

            # 保存工件到本地存储
            # 保存工件内容
            content_path = self.storage_path / "artifacts.md"

            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(self.show())

        
        return artifact
    
    def show(self) -> str:
        """
        显示所有工件的名称、路径和摘要
        
        Returns:
            str: 以Markdown格式返回所有工件信息
        """
        if not self.artifacts_content:
            return ""
        
        markdown_content = "# 已完成任务列表\n\n"
        
        for i, artifact in enumerate(self.artifacts_content, 1):
            markdown_content += f"## {i}. 任务ID: {artifact.artifact_id}\n\n"
            
            # 工件名称
            name = artifact.metadata.get('name', artifact.artifact_id) if artifact.metadata else artifact.artifact_id
            markdown_content += f"**名称**: {name}\n\n"
            
            # 工件路径
            path = artifact.content_location or "内存中存储"
            markdown_content += f"**路径**: {path}\n\n"
            
            # 工件摘要
            summary = artifact.summary or "无摘要"
            markdown_content += f"**摘要**: {summary}\n\n"
        
            markdown_content += "---\n\n"
        
        return markdown_content
