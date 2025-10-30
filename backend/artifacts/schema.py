from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass

class ArtifactType(Enum):
    """工件类型枚举"""
    FILE = "file"
    IMAGE = "image"
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"
    OTHER = "other"

class ArtifactFileSize(Enum):
    """工件文件大小枚举"""
    SMALL = "small"      # <1MB
    MEDIUM = "medium"    # 1MB-10MB
    LARGE = "large"      # >10MB

@dataclass
class ArtifactSchema:
    artifact_id: str
    artifact_type: ArtifactType
    metadata: Dict[str, Any]
    summary: Optional[str] = None
    content: Optional[Any] = None
    content_location: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tags: Optional[List[str]] = None
    file_size: Optional[ArtifactFileSize] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type.value,
            "metadata": self.metadata,
            "summary": self.summary,
            "content": self.content,
            "content_location": self.content_location,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }