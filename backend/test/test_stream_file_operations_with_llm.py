"""
使用LLM进行流式文件修改的测试
参考 test_shell_execute_with_llm.py 的实现方式
"""

from datetime import datetime
import os
import sys
import json
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from backend.llm.llm import OpenAILLM, LLMConfig
from backend.tools.stream_file_operations import StreamFileOperationTool
from backend.llm.base import Message, MessageRole


# ============================================================================
# 测试用的复杂长文件内容
# ============================================================================

COMPLEX_PYTHON_FILE = '''"""
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
    def validate_email(email: str) -> bool:
        """验证邮箱格式"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
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
'''


async def create_test_file(test_dir: Path) -> Path:
    """创建复杂的测试文件"""
    test_file = test_dir / "user_service.py"
    test_file.write_text(COMPLEX_PYTHON_FILE, encoding="utf-8")

    lines = COMPLEX_PYTHON_FILE.split('\n')
    print(f"✓ 创建测试文件: {test_file}")
    print(f"  文件行数: {len(lines)}")
    print(f"  文件大小: {len(COMPLEX_PYTHON_FILE)} 字节")

    return test_file


async def test_stream_file_operation_with_llm():
    """使用LLM测试流式文件修改（工具调用方式）"""

    print("="*70)
    print("使用LLM进行流式文件修改测试")
    print("="*70)

    # 创建测试目录和文件
    test_dir = Path("test_output")
    test_dir.mkdir(exist_ok=True)
    test_file = await create_test_file(test_dir)

    # 读取文件内容
    file_content = test_file.read_text()
    lines = file_content.split('\n')

    # 显示要修改的部分（validate_email方法，约第97-100行）
    print("\n要修改的代码片段（第97-100行）:")
    for i in range(96, min(100, len(lines))):
        print(f"  {i+1}: {lines[i]}")

    # 初始化工具
    file_tool = StreamFileOperationTool()

    # LLM配置
    llm_config = LLMConfig(
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        max_tokens=64000,
        stream=True,
        tools=[file_tool]
    )

    try:
        llm = OpenAILLM(llm_config)
        print(f"\n✓ LLM初始化成功")
    except Exception as e:
        print(f"\n❌ LLM初始化失败: {e}")
        print("  跳过LLM测试，运行模拟测试...")
        await run_mock_test(test_file)
        return

    # 构建用户消息
    user_msg = Message(
        role=MessageRole.USER,
        content=f"""请帮我修改文件 {test_file} 中的 validate_email 方法（第97-100行）。

要求：
1. 增强邮箱验证功能，添加更多检查
2. 添加详细的docstring说明
3. 添加参数类型检查

请使用 stream_file_operation 工具来完成修改。使用 modify 模式，start_line=97, end_line=100。

当前文件内容（第95-105行）：
```python
{chr(10).join(lines[94:105])}
```
""",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        metadata={"current_round": 0}
    )

    tool_calls = []
    current_round = 0
    conversation = [user_msg]
    max_rounds = 5

    print(f"\n开始与LLM对话...")

    while current_round < max_rounds:
        print(f"\n--- 第 {current_round + 1} 轮 ---")

        cur_content = ""
        async for chunk in await llm.generate(conversation):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                cur_content += chunk.content

            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)

        if tool_calls:
            print("\n\n检测到工具调用:")
            conversation.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=cur_content,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tool_calls=tool_calls,
                    metadata={"current_round": current_round}
                )
            )

            for tool_call in tool_calls:
                print(f"  工具: {tool_call.function['name']}")
                print(f"  参数: {tool_call.function['arguments']}")

                arguments = json.loads(tool_call.function['arguments'])

                # 执行工具
                async for tool_result in file_tool.execute(**arguments):
                    print(f"\n工具结果: {tool_result}")
                    conversation.append(
                        Message(
                            role=MessageRole.TOOL,
                            content=str(tool_result),
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            tool_call_id=tool_call.id,
                            metadata={"current_round": current_round}
                        )
                    )

            tool_calls = []
            cur_content = ""
        else:
            # 没有工具调用，对话结束
            if cur_content:
                print("\n\nLLM完成响应，无更多工具调用")
            break

        current_round += 1

    # 验证结果
    print("\n" + "="*70)
    print("验证修改结果")
    print("="*70)

    final_content = test_file.read_text()
    final_lines = final_content.split('\n')

    print(f"\n修改后文件行数: {len(final_lines)}")
    print(f"\n修改后的 validate_email 方法区域:")
    # 找到 validate_email 方法
    for i, line in enumerate(final_lines):
        if 'def validate_email' in line:
            # 打印方法及其后续几行
            for j in range(i, min(i+15, len(final_lines))):
                print(f"  {j+1}: {final_lines[j]}")
            break

    # 验证语法
    print("\n验证Python语法...")
    try:
        compile(final_content, test_file.name, 'exec')
        print("✓ 语法正确!")
    except SyntaxError as e:
        print(f"❌ 语法错误: {e}")


async def run_mock_test(test_file: Path):
    """运行模拟测试（不需要API密钥）"""
    print("\n" + "="*70)
    print("运行模拟测试")
    print("="*70)

    # 读取原始文件
    original_content = test_file.read_text()
    original_lines = original_content.split('\n')

    # 找到 validate_email 方法的实际行号
    start_line = None
    end_line = None
    for i, line in enumerate(original_lines, 1):
        if 'def validate_email' in line and start_line is None:
            start_line = i
        if start_line and 'def validate_username' in line:
            end_line = i - 1  # validate_username 前一行
            break

    if not start_line or not end_line:
        print("❌ 无法找到 validate_email 方法")
        return

    print(f"\n原始文件行数: {len(original_lines)}")
    print(f"\n要修改的代码（第{start_line}-{end_line}行）:")
    for i in range(start_line - 1, end_line):
        print(f"  {i+1}: {original_lines[i]}")

    # 模拟LLM生成的新内容（末尾包含重复 - validate_username 的声明）
    mock_new_content = '''    @staticmethod
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
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_username(username: str) -> bool:'''

    print(f"\n模拟LLM生成的内容（注意末尾有重复行）:")
    mock_lines = mock_new_content.split('\n')
    for i, line in enumerate(mock_lines, 1):
        marker = " ← 重复" if "validate_username" in line else ""
        print(f"  {i}: {line}{marker}")

    # 使用工具进行修改
    tool = StreamFileOperationTool()

    print(f"\n执行修改操作...")

    # 开始修改
    async for result in tool.execute(
        filepath=str(test_file),
        operation_mode="modify",
        start_line=start_line,
        end_line=end_line,
        status="start",
        auto_deduplicate=True,
        show_diff=True
    ):
        print(f"  {result}")

    # 模拟流式写入
    chunk_size = 50
    for i in range(0, len(mock_new_content), chunk_size):
        chunk = mock_new_content[i:i+chunk_size]
        await tool.write_chunk(chunk)

    # 完成修改
    async for result in tool.execute(filepath=str(test_file), status="end"):
        print(result)

    # 验证结果
    final_content = test_file.read_text()
    final_lines = final_content.split('\n')

    print(f"\n📊 结果统计:")
    print(f"  原始文件行数: {len(original_lines)}")
    print(f"  修改后行数: {len(final_lines)}")
    print(f"  行数变化: {len(final_lines) - len(original_lines):+d}")

    print(f"\n修改后的 validate_email 方法:")
    for i, line in enumerate(final_lines):
        if 'def validate_email' in line:
            for j in range(i, min(i+25, len(final_lines))):
                print(f"  {j+1}: {final_lines[j]}")
                # 到下一个方法定义时停止
                if j > i and 'def ' in final_lines[j] and 'validate_email' not in final_lines[j]:
                    break
            break

    # 验证语法
    print("\n验证Python语法...")
    try:
        compile(final_content, test_file.name, 'exec')
        print("✓ 语法正确!")
    except SyntaxError as e:
        print(f"❌ 语法错误: {e}")


async def main():
    """主函数"""
    test_dir = Path("test_output")
    test_dir.mkdir(exist_ok=True)

    # if args.mock:
    #     test_file = await create_test_file(test_dir)
    #     await run_mock_test(test_file)
    # elif args.llm:
    #     await test_stream_file_operation_with_llm()
    # else:
    #     # 默认运行模拟测试
    #     test_file = await create_test_file(test_dir)
    #     await run_mock_test(test_file)
    await test_stream_file_operation_with_llm()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
