"""
Memory模块：提供记忆管理功能
"""

from .base import (
    MemoryItem,
    BaseMemory,
)

from .schema import (
    # 枚举类型
    UserLanguage,
    UserRole,
    ResearchDomain,
    OutputFormat,
    DetailLevel,
    InteractionStyle,
    LearningStyle,
    
    # 数据模型
    UserBasicInfo,
    LanguagePreference,
    ResearchPreference,
    OutputPreference,
    InteractionPreference,
    WorkflowPreference,
    BehaviorPattern,
    LearningProgress,
    AdaptiveSettings,
    PersonalizationTags,
    UserProfile,
    
    # 情节记忆模型
    EpisodicMemory,
    EpisodeType,
    ImportanceLevel,
)

from .longmem import (
    # 核心接口
    DatabaseInterface,
    MemoryCache,
    
    # 管理器类
    UserProfileManager,
    EpisodicMemoryManager,
    LongTermMemoryManager,

)

__all__ = [
    # 基础记忆类
    "MemoryItem",
    "MemoryContext",
    "BaseMemory",
    
    # 用户画像枚举
    "UserLanguage",
    "UserRole",
    "ResearchDomain",
    "OutputFormat",
    "DetailLevel",
    "InteractionStyle",
    "LearningStyle",
    
    # 情节记忆枚举
    "EpisodeType",
    "ImportanceLevel",
    
    # 用户画像数据模型
    "UserBasicInfo",
    "LanguagePreference",
    "ResearchPreference",
    "OutputPreference",
    "InteractionPreference",
    "WorkflowPreference",
    "BehaviorPattern",
    "LearningProgress",
    "AdaptiveSettings",
    "PersonalizationTags",
    "UserProfile",
    
    # 情节记忆模型
    "EpisodicMemory",
    
    # 核心接口和缓存
    "DatabaseInterface",
    "MemoryCache",
    
    # 管理器类
    "UserProfileManager",
    "EpisodicMemoryManager",
    "LongTermMemoryManager",
    
    # 工厂函数和工具
    "create_memory_manager",
    "MockDatabaseInterface",
]