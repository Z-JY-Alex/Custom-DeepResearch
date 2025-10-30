"""
长期记忆管理器
提供用户画像和情节记忆的存储、获取、搜索等功能
支持数据库持久化和缓存优化
"""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Union, Tuple
from loguru import logger

from .schema import (
    UserProfile, 
    EpisodicMemory,
    UserRole,
    EpisodeType,
    ImportanceLevel,
    UserBasicInfo,
)


class DatabaseInterface(ABC):
    """数据库接口抽象类"""
    
    @abstractmethod
    async def save_user_profile(self, profile: UserProfile) -> bool:
        """保存用户画像"""
        pass
    
    @abstractmethod
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        pass
    
    @abstractmethod
    async def update_user_profile(self, user_id: str, profile: UserProfile) -> bool:
        """更新用户画像"""
        pass
    
    @abstractmethod
    async def delete_user_profile(self, user_id: str) -> bool:
        """删除用户画像"""
        pass
    
    @abstractmethod
    async def save_episodic_memory(self, memory: EpisodicMemory) -> bool:
        """保存情节记忆"""
        pass
    
    @abstractmethod
    async def get_episodic_memory(self, episode_id: str) -> Optional[EpisodicMemory]:
        """获取单个情节记忆"""
        pass
    
    @abstractmethod
    async def search_episodic_memories(
        self, 
        user_id: str,
        query: Optional[str] = None,
        episode_type: Optional[EpisodeType] = None,
        importance_level: Optional[ImportanceLevel] = None,
        tags: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[EpisodicMemory]:
        """搜索情节记忆"""
        pass
    
    @abstractmethod
    async def update_episodic_memory(self, episode_id: str, memory: EpisodicMemory) -> bool:
        """更新情节记忆"""
        pass
    
    @abstractmethod
    async def delete_episodic_memory(self, episode_id: str) -> bool:
        """删除情节记忆"""
        pass


class MemoryCache:
    """内存缓存管理器"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        初始化缓存
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存存活时间(秒)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, datetime] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key not in self._cache:
            return None
        
        # 检查TTL
        if self._is_expired(key):
            self._remove(key)
            return None
        
        # 更新访问时间
        self._access_times[key] = datetime.now()
        return self._cache[key]['data']
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        # 检查缓存大小，必要时清理
        if len(self._cache) >= self.max_size:
            self._evict_lru()
        
        self._cache[key] = {
            'data': value,
            'created_at': datetime.now()
        }
        self._access_times[key] = datetime.now()
    
    def remove(self, key: str) -> None:
        """移除缓存项"""
        self._remove(key)
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._access_times.clear()
    
    def _is_expired(self, key: str) -> bool:
        """检查缓存是否过期"""
        if key not in self._cache:
            return True
        
        created_at = self._cache[key]['created_at']
        return (datetime.now() - created_at).total_seconds() > self.ttl
    
    def _remove(self, key: str) -> None:
        """移除缓存项"""
        self._cache.pop(key, None)
        self._access_times.pop(key, None)
    
    def _evict_lru(self) -> None:
        """移除最近最少使用的缓存项"""
        if not self._access_times:
            return
        
        lru_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
        self._remove(lru_key)


class UserProfileManager:
    """用户画像管理器"""
    
    def __init__(self, db: DatabaseInterface, cache: Optional[MemoryCache] = None):
        """
        初始化用户画像管理器
        Args:
            db: 数据库接口
            cache: 缓存管理器
        """
        self.db = db
        self.cache = cache or MemoryCache()
        logger.info("用户画像管理器初始化完成")
    
    async def create_user_profile(
        self, 
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role: UserRole = UserRole.OTHER,
        **kwargs
    ) -> UserProfile:
        """
        创建新的用户画像
        Args:
            user_id: 用户ID，如果不提供则自动生成
            username: 用户名
            email: 邮箱
            role: 用户角色
            **kwargs: 其他用户信息
        Returns:
            UserProfile: 创建的用户画像
        """
        if not user_id:
            user_id = str(uuid.uuid4())
        
        # 创建基础信息
        basic_info = UserBasicInfo(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            **{k: v for k, v in kwargs.items() if k in UserBasicInfo.__fields__}
        )
        
        # 创建用户画像
        profile = UserProfile(basic_info=basic_info)
        
        # 保存到数据库
        success = await self.db.save_user_profile(profile)
        if success:
            # 添加到缓存
            self.cache.set(f"profile:{user_id}", profile)
            logger.info(f"成功创建用户画像: {user_id}")
            return profile
        else:
            raise Exception(f"保存用户画像失败: {user_id}")
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """
        获取用户画像
        Args:
            user_id: 用户ID
        Returns:
            Optional[UserProfile]: 用户画像，如果不存在则返回None
        """
        # 首先尝试从缓存获取
        cache_key = f"profile:{user_id}"
        cached_profile = self.cache.get(cache_key)
        if cached_profile:
            logger.debug(f"从缓存获取用户画像: {user_id}")
            return cached_profile
        
        # 从数据库获取
        profile = await self.db.get_user_profile(user_id)
        if profile:
            # 添加到缓存
            self.cache.set(cache_key, profile)
            logger.debug(f"从数据库获取用户画像: {user_id}")
        
        return profile
    
    async def update_user_profile(
        self, 
        user_id: str, 
        updates: Dict[str, Any]
    ) -> Optional[UserProfile]:
        """
        更新用户画像
        """
        pass



class EpisodicMemoryManager:
    """情节记忆管理器"""
    
    def __init__(self, db: DatabaseInterface, cache: Optional[MemoryCache] = None):
        """
        初始化情节记忆管理器
        Args:
            db: 数据库接口
            cache: 缓存管理器
        """
        self.db = db
        self.cache = cache or MemoryCache()
        logger.info("情节记忆管理器初始化完成")
    
    
    async def get_episodic_memory(self, episode_id: str) -> Optional[EpisodicMemory]:
        """
        获取单个情节记忆
        Args:
            episode_id: 情节ID
        Returns:
            Optional[EpisodicMemory]: 情节记忆，如果不存在则返回None
        """
        # 首先尝试从缓存获取
        cache_key = f"episode:{episode_id}"
        cached_memory = self.cache.get(cache_key)
        if cached_memory:
            logger.debug(f"从缓存获取情节记忆: {episode_id}")
            return cached_memory
        
        # 从数据库获取
        memory = await self.db.get_episodic_memory(episode_id)
        if memory:
            # 添加到缓存
            self.cache.set(cache_key, memory)
            logger.debug(f"从数据库获取情节记忆: {episode_id}")
        
        return memory
    
    async def search_episodic_memories(
        self,
        user_id: str,
        query: Optional[str] = None,
        episode_type: Optional[EpisodeType] = None,
        importance_level: Optional[ImportanceLevel] = None,
        tags: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[EpisodicMemory]:
        """
        搜索情节记忆
       
        """
        pass
    
    async def update_episodic_memory(
        self,
        episode_id: str,
        updates: Dict[str, Any]
    ) -> Optional[EpisodicMemory]:
        """
        更新情节记忆
       
        """
        pass
    
    async def delete_episodic_memory(self, episode_id: str) -> bool:
        """
        删除情节记忆
        """
        pass


class LongTermMemoryManager:
    """长期记忆管理器 - 统一管理用户画像和情节记忆"""
    
    def __init__(self, db: DatabaseInterface, cache_size: int = 1000, cache_ttl: int = 3600):
        """
        初始化长期记忆管理器
        Args:
            db: 数据库接口
            cache_size: 缓存大小
            cache_ttl: 缓存存活时间(秒)
        """
        self.db = db
        self.cache = MemoryCache(max_size=cache_size, ttl=cache_ttl)
        
        # 初始化子管理器
        self.user_profile_manager = UserProfileManager(db, self.cache)
        self.episodic_memory_manager = EpisodicMemoryManager(db, self.cache)
        
        logger.info("长期记忆管理器初始化完成")
    
    