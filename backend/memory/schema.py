"""
用户画像Schema定义模块
用于定义用户的基础信息、偏好风格、研究习惯等数据结构
同时包含情节记忆(Episodic Memory)的定义
"""

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field, validator


class UserLanguage(str, Enum):
    """用户语言偏好枚举"""
    CHINESE = "zh-CN"
    ENGLISH = "en-US"
    JAPANESE = "ja-JP"
    KOREAN = "ko-KR"
    FRENCH = "fr-FR"
    GERMAN = "de-DE"
    SPANISH = "es-ES"
    RUSSIAN = "ru-RU"


class UserRole(str, Enum):
    """用户角色枚举"""
    STUDENT = "student"           # 学生
    RESEARCHER = "researcher"     # 研究人员
    TEACHER = "teacher"          # 教师
    ENGINEER = "engineer"        # 工程师
    ANALYST = "analyst"          # 分析师
    MANAGER = "manager"          # 管理者
    DEVELOPER = "developer"      # 开发者
    CONSULTANT = "consultant"    # 顾问
    JOURNALIST = "journalist"    # 记者
    OTHER = "other"              # 其他


class ResearchDomain(str, Enum):
    """研究领域枚举"""
    TECHNOLOGY = "technology"            # 科技
    SCIENCE = "science"                  # 科学
    BUSINESS = "business"                # 商业
    EDUCATION = "education"              # 教育
    MEDICINE = "medicine"                # 医学
    LAW = "law"                         # 法律
    FINANCE = "finance"                 # 金融
    ARTS = "arts"                       # 艺术
    HISTORY = "history"                 # 历史
    POLITICS = "politics"               # 政治
    ENVIRONMENT = "environment"         # 环境
    PSYCHOLOGY = "psychology"           # 心理学
    SOCIOLOGY = "sociology"             # 社会学
    PHILOSOPHY = "philosophy"           # 哲学
    ENGINEERING = "engineering"         # 工程
    MATHEMATICS = "mathematics"         # 数学
    LITERATURE = "literature"           # 文学
    OTHER = "other"                     # 其他


class OutputFormat(str, Enum):
    """输出格式偏好枚举"""
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    JSON = "json"
    PLAIN_TEXT = "plain_text"
    STRUCTURED = "structured"


class DetailLevel(str, Enum):
    """详细程度偏好枚举"""
    BRIEF = "brief"           # 简要
    MODERATE = "moderate"     # 适中
    DETAILED = "detailed"     # 详细
    COMPREHENSIVE = "comprehensive"  # 全面


class InteractionStyle(str, Enum):
    """交互风格枚举"""
    FORMAL = "formal"         # 正式
    CASUAL = "casual"         # 随意
    PROFESSIONAL = "professional"  # 专业
    FRIENDLY = "friendly"     # 友好
    DIRECT = "direct"         # 直接


class LearningStyle(str, Enum):
    """学习风格枚举"""
    VISUAL = "visual"         # 视觉型
    AUDITORY = "auditory"     # 听觉型
    KINESTHETIC = "kinesthetic"  # 动手型
    READING = "reading"       # 阅读型
    MIXED = "mixed"           # 混合型


class EpisodeType(str, Enum):
    """情节类型枚举"""
    EXPERIENCE = "experience"       # 个人经历
    EVENT = "event"                # 事件
    STORY = "story"                # 故事
    MEMORY = "memory"              # 回忆
    OTHER = "other"                # 其他


class ImportanceLevel(str, Enum):
    """重要性级别枚举"""
    LOW = "low"           # 低
    MEDIUM = "medium"     # 中
    HIGH = "high"         # 高


class UserBasicInfo(BaseModel):
    """用户基础信息"""
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="用户唯一标识")
    username: Optional[str] = Field(default=None, description="用户名")
    email: Optional[str] = Field(default=None, description="邮箱")
    real_name: Optional[str] = Field(default=None, description="真实姓名")
    role: UserRole = Field(default=UserRole.OTHER, description="用户角色")
    organization: Optional[str] = Field(default=None, description="所属组织/机构")
    title: Optional[str] = Field(default=None, description="职位/头衔")
    location: Optional[str] = Field(default=None, description="地理位置")
    timezone: str = Field(default="UTC", description="时区")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_active: datetime = Field(default_factory=datetime.now, description="最后活跃时间")
    
    class Config:
        arbitrary_types_allowed = True


class LanguagePreference(BaseModel):
    """语言偏好设置"""
    primary_language: UserLanguage = Field(default=UserLanguage.CHINESE, description="主要语言")
    secondary_languages: List[UserLanguage] = Field(default_factory=list, description="次要语言")
    auto_translate: bool = Field(default=False, description="是否自动翻译")
    translation_quality: str = Field(default="high", description="翻译质量要求")


class ResearchPreference(BaseModel):
    """研究偏好设置"""
    primary_domains: List[ResearchDomain] = Field(default_factory=list, description="主要研究领域")
    secondary_domains: List[ResearchDomain] = Field(default_factory=list, description="次要研究领域")
    preferred_sources: List[str] = Field(default_factory=list, description="偏好的信息源")
    excluded_sources: List[str] = Field(default_factory=list, description="排除的信息源")
    research_depth: DetailLevel = Field(default=DetailLevel.MODERATE, description="研究深度偏好")
    time_sensitivity: bool = Field(default=False, description="是否对时效性敏感")
    fact_checking_level: str = Field(default="normal", description="事实核查要求")


class OutputPreference(BaseModel):
    """输出偏好设置"""
    preferred_format: OutputFormat = Field(default=OutputFormat.MARKDOWN, description="偏好的输出格式")
    detail_level: DetailLevel = Field(default=DetailLevel.MODERATE, description="详细程度偏好")
    include_sources: bool = Field(default=True, description="是否包含信息源")
    include_images: bool = Field(default=True, description="是否包含图片")
    include_charts: bool = Field(default=True, description="是否包含图表")
    max_length: Optional[int] = Field(default=None, description="最大长度限制")
    structure_preference: List[str] = Field(default_factory=list, description="结构偏好")


class InteractionPreference(BaseModel):
    """交互偏好设置"""
    interaction_style: InteractionStyle = Field(default=InteractionStyle.PROFESSIONAL, description="交互风格")
    learning_style: LearningStyle = Field(default=LearningStyle.MIXED, description="学习风格")
    feedback_frequency: str = Field(default="normal", description="反馈频率")
    progress_tracking: bool = Field(default=True, description="是否跟踪进度")
    interruption_tolerance: str = Field(default="medium", description="打断容忍度")
    question_asking_style: str = Field(default="guided", description="提问风格")


class WorkflowPreference(BaseModel):
    """工作流程偏好"""
    planning_style: str = Field(default="structured", description="规划风格")
    task_granularity: str = Field(default="medium", description="任务粒度偏好")
    parallel_processing: bool = Field(default=True, description="是否支持并行处理")
    auto_optimization: bool = Field(default=True, description="是否自动优化")
    review_frequency: str = Field(default="periodic", description="回顾频率")
    checkpoint_preference: bool = Field(default=True, description="是否设置检查点")


class BehaviorPattern(BaseModel):
    """行为模式数据"""
    session_count: int = Field(default=0, description="会话次数")
    total_queries: int = Field(default=0, description="总查询次数")
    avg_session_duration: float = Field(default=0.0, description="平均会话时长(分钟)")
    preferred_time_slots: List[str] = Field(default_factory=list, description="偏好的时间段")
    common_query_types: Dict[str, int] = Field(default_factory=dict, description="常见查询类型统计")
    tool_usage_stats: Dict[str, int] = Field(default_factory=dict, description="工具使用统计")
    success_rate: float = Field(default=0.0, description="任务成功率")
    satisfaction_score: float = Field(default=0.0, description="满意度评分")
    
    class Config:
        arbitrary_types_allowed = True


class LearningProgress(BaseModel):
    """学习进度追踪"""
    knowledge_areas: Dict[str, float] = Field(default_factory=dict, description="知识领域掌握度")
    skill_levels: Dict[str, str] = Field(default_factory=dict, description="技能水平")
    learning_goals: List[str] = Field(default_factory=list, description="学习目标")
    completed_tasks: List[str] = Field(default_factory=list, description="已完成任务")
    learning_path: List[str] = Field(default_factory=list, description="学习路径")
    milestones: List[Dict[str, Any]] = Field(default_factory=list, description="里程碑")
    
    class Config:
        arbitrary_types_allowed = True


class AdaptiveSettings(BaseModel):
    """自适应设置"""
    auto_personalization: bool = Field(default=True, description="是否自动个性化")
    learning_rate: float = Field(default=0.1, description="学习率")
    adaptation_frequency: str = Field(default="session", description="适应频率")
    min_confidence_threshold: float = Field(default=0.6, description="最小置信度阈值")
    max_history_length: int = Field(default=1000, description="最大历史记录长度")
    feedback_weight: float = Field(default=0.3, description="反馈权重")


class PersonalizationTags(BaseModel):
    """个性化标签"""
    expertise_tags: Set[str] = Field(default_factory=set, description="专业领域标签")
    interest_tags: Set[str] = Field(default_factory=set, description="兴趣标签")
    behavioral_tags: Set[str] = Field(default_factory=set, description="行为标签")
    preference_tags: Set[str] = Field(default_factory=set, description="偏好标签")
    context_tags: Set[str] = Field(default_factory=set, description="上下文标签")
    
    class Config:
        arbitrary_types_allowed = True
    
    @validator('expertise_tags', 'interest_tags', 'behavioral_tags', 'preference_tags', 'context_tags', pre=True)
    def convert_set_to_list(cls, v):
        if isinstance(v, set):
            return v
        elif isinstance(v, list):
            return set(v)
        return set()


class UserProfile(BaseModel):
    """用户画像主模型"""
    
    # 基础信息
    basic_info: UserBasicInfo = Field(default_factory=UserBasicInfo, description="基础信息")
    
    # 偏好设置
    language_preference: LanguagePreference = Field(default_factory=LanguagePreference, description="语言偏好")
    research_preference: ResearchPreference = Field(default_factory=ResearchPreference, description="研究偏好")
    output_preference: OutputPreference = Field(default_factory=OutputPreference, description="输出偏好")
    interaction_preference: InteractionPreference = Field(default_factory=InteractionPreference, description="交互偏好")
    workflow_preference: WorkflowPreference = Field(default_factory=WorkflowPreference, description="工作流偏好")
    
    # 行为分析
    behavior_pattern: BehaviorPattern = Field(default_factory=BehaviorPattern, description="行为模式")
    learning_progress: LearningProgress = Field(default_factory=LearningProgress, description="学习进度")
    
    # 系统设置
    adaptive_settings: AdaptiveSettings = Field(default_factory=AdaptiveSettings, description="自适应设置")
    personalization_tags: PersonalizationTags = Field(default_factory=PersonalizationTags, description="个性化标签")
    
    # 元数据
    version: str = Field(default="1.0", description="画像版本")
    last_updated: datetime = Field(default_factory=datetime.now, description="最后更新时间")
    update_count: int = Field(default=0, description="更新次数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            set: lambda v: list(v)
        }
    

# ==================== 情节记忆相关模型 ====================

class EpisodicMemory(BaseModel):
    """情节记忆模型 - 用于存储用户提到的经历、事件等内容"""
    
    # 基础信息
    episode_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="情节ID")
    user_id: str = Field(..., description="用户ID")
    title: str = Field(..., description="情节标题")
    content: str = Field(..., description="情节内容描述")
    
    # 分类和标签
    episode_type: EpisodeType = Field(default=EpisodeType.OTHER, description="情节类型")
    importance_level: ImportanceLevel = Field(default=ImportanceLevel.MEDIUM, description="重要性级别")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    
    # 时间信息
    occurred_time: Optional[datetime] = Field(default=None, description="事件发生时间")
    created_time: datetime = Field(default_factory=datetime.now, description="记录创建时间")
    updated_time: datetime = Field(default_factory=datetime.now, description="最后更新时间")
    
    # 上下文信息
    location: Optional[str] = Field(default=None, description="发生地点")
    participants: List[str] = Field(default_factory=list, description="参与者")
    related_topics: List[str] = Field(default_factory=list, description="相关话题")
    
    # 情感和评价
    emotion: Optional[str] = Field(default=None, description="情感色彩")
    sentiment_score: Optional[float] = Field(default=None, description="情感评分 (-1到1)")
    personal_significance: Optional[str] = Field(default=None, description="个人意义")
    
    # 元数据
    source: str = Field(default="user_input", description="信息来源")
    confidence: float = Field(default=1.0, description="置信度")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
