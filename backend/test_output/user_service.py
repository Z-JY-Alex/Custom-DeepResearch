"""
用户管理服务模块
提供用户的创建、查询、更新、删除等功能
"""

import hashlib
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import re


class UserStatus(Enum):
    """用户状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class UserRole(Enum):
    """用户角色枚举"""
    ADMIN = "admin"
    MODERATOR = "moderator"
    PREMIUM_USER = "premium_user"
    REGULAR_USER = "regular_user"
    GUEST = "guest"


@dataclass
class UserProfile:
    """用户资料数据类"""
    nickname: str = ""
    avatar_url: str = ""
    bio: str = ""
    location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "nickname": self.nickname,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "location": self.location
        }


@dataclass
class User:
    """用户数据类"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    email: str = ""
    password_hash: str = ""
    status: UserStatus = UserStatus.ACTIVE
    role: UserRole = UserRole.REGULAR_USER
    profile: UserProfile = field(default_factory=UserProfile)
    created_at: datetime = field(default_factory=datetime.now)


class UserService:
    """用户服务类"""

    def __init__(self):
        """初始化用户服务"""
        self._users: Dict[str, User] = {}
        self._email_index: Dict[str, str] = {}

    @staticmethod
    def hash_password(password: str) -> str:
        """密码哈希"""
        salt = "user_service_salt_2024"
        return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()

    @staticmethod
    @staticmethod
    def validate_email(email: str) -> bool:
        """验证邮箱格式

        Args:
            email: 待验证的邮箱地址

        Returns:
            bool: 邮箱格式是否有效

        Raises:
            TypeError: 如果email不是字符串类型
        """
        if not isinstance(email, str):
            raise TypeError("email必须是字符串类型")
        if not email or len(email) > 254:
            return False
    def validate_username(username: str) -> bool:
        """验证用户名格式"""
        if len(username) < 3 or len(username) > 20:
            return False
        pattern = r'^[a-zA-Z][a-zA-Z0-9_]*$'
        return bool(re.match(pattern, username))

    def create_user(self, username: str, email: str, password: str) -> User:
        """创建用户"""
        if not self.validate_username(username):
            raise ValueError("用户名格式无效")
        if not self.validate_email(email):
            raise ValueError("邮箱格式无效")

        user = User(
            username=username,
            email=email,
            password_hash=self.hash_password(password)
        )
        self._users[user.id] = user
        self._email_index[email.lower()] = user.id
        return user

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据ID获取用户"""
        return self._users.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        user_id = self._email_index.get(email.lower())
        if user_id:
            return self._users.get(user_id)
        return None

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """用户认证"""
        user = self.get_user_by_email(email)
        if not user:
            return None
        if user.password_hash != self.hash_password(password):
            return None
        return user

    def list_users(self, page: int = 1, page_size: int = 20) -> List[User]:
        """列出用户"""
        users = list(self._users.values())
        start = (page - 1) * page_size
        end = start + page_size
        return users[start:end]


# 导出
__all__ = ["UserStatus", "UserRole", "UserProfile", "User", "UserService"]
