"""
用户交互工具
支持AI主动询问用户，获取用户输入和选择
"""

import json
from typing import List

from backend.tools.base import BaseTool


class UserInteractionTool(BaseTool):
    """用户交互工具 - 用于AI主动询问用户信息"""
    
    name: str = "ask_user"
    description: str = """当需要用户提供额外信息时，使用此工具询问用户。

使用场景：
- 任务信息不明确，需要用户澄清
- 存在多种方案选择，需要用户决策
- 需要用户确认敏感操作
- 缺少必要参数，需要用户提供

支持的问题类型：
- text: 文本输入题
- choice: 单选题
- confirm: 确认题（是/否）

注意事项：
- 问题要具体明确，避免模糊询问
- 提供选项时要给出清晰的选择理由
- 一次只询问一个核心问题
- 设置合理的超时时间
"""
    
    parameters: dict = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "要询问用户的具体问题，要清晰明确"
            },
            "question_type": {
                "type": "string",
                "enum": ["text", "choice", "confirm"],
                "description": "问题类型：text=文本输入，choice=单选题，confirm=确认题",
                "default": "text"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "选择题的选项列表（仅当question_type为choice时使用）"
            },
            "timeout": {
                "type": "integer",
                "description": "等待用户回答的超时时间（秒），默认300秒",
                "default": 300,
                "minimum": 30,
                "maximum": 1800
            },
            "required": {
                "type": "boolean",
                "description": "是否必须回答才能继续执行，默认true",
                "default": True
            },
            "context": {
                "type": "string",
                "description": "问题的上下文说明，帮助用户理解问题背景"
            }
        },
        "required": ["question"]
    }


    async def execute(self, **kwargs) -> str:
        """执行用户交互（直接返回结果，不做中间流式输出）"""
        question = kwargs.get("question", "")
        question_type = kwargs.get("question_type", "text")
        options = kwargs.get("options", [])


        if not question.strip():
            return "❌ 错误：问题内容不能为空"

        # 验证选择题必须有选项
        if question_type == "choice" and not options:
            return "❌ 错误：选择题必须提供选项列表"

        # 验证选项数量
        if question_type == "choice" and len(options) < 2:
            return "❌ 错误：选择题至少需要2个选项"

        # 构建返回数据
        result_data = {
            "question": question,
            "question_type": question_type,
        }

        # 根据问题类型添加选项
        if question_type == "choice":
            result_data["options"] = options
        elif question_type == "confirm":
            result_data["options"] = ["yes", "no"]
        else:  # text
            result_data["options"] = []

        # 返回 JSON 字符串，避免元组类型导致的字符串拼接错误
        return json.dumps(result_data, ensure_ascii=False)

    
    def _get_default_answer(self, question_type: str, options: List[str]) -> str:
        """获取默认回答"""
        if question_type == "choice" and options:
            return options[0]  # 返回第一个选项
        elif question_type == "confirm":
            return "no"  # 默认否定
        else:
            return "跳过"  # 文本题默认跳过
    
    