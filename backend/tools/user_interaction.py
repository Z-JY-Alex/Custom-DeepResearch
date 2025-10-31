"""
用户交互工具
支持AI主动询问用户，获取用户输入和选择
"""

import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from loguru import logger

from backend.tools.base import BaseTool
from backend.interaction.manager import InteractionManager


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
    
    def __init__(self, interaction_manager: Optional[InteractionManager] = None, session_id: str = None):
        super().__init__()
        self.interaction_manager = interaction_manager
        self.session_id = session_id
    
    async def execute(self, **kwargs) -> AsyncGenerator[str, None]:
        """执行用户交互"""
        question = kwargs.get("question", "")
        question_type = kwargs.get("question_type", "text")
        options = kwargs.get("options", [])
        timeout = kwargs.get("timeout", 300)
        required = kwargs.get("required", True)
        context = kwargs.get("context", "")
        
        if not question.strip():
            yield "❌ 错误：问题内容不能为空"
            return
        
        # 验证选择题必须有选项
        if question_type == "choice" and not options:
            yield "❌ 错误：选择题必须提供选项列表"
            return
        
        # 验证选项数量
        if question_type == "choice" and len(options) < 2:
            yield "❌ 错误：选择题至少需要2个选项"
            return
        
        if not self.interaction_manager:
            yield "❌ 错误：交互管理器未配置，无法询问用户"
            return
        
        if not self.session_id:
            yield "❌ 错误：会话ID未设置，无法询问用户"
            return
        
        try:
            # 创建交互
            interaction_id, future = await self.interaction_manager.create_interaction(
                session_id=self.session_id,
                question=question,
                question_type=question_type,
                options=options,
                timeout=timeout,
                required=required
            )
            
            # 构建问题事件数据
            question_event = {
                "event_type": "user_question",
                "interaction_id": interaction_id,
                "session_id": self.session_id,
                "question": question,
                "question_type": question_type,
                "options": options,
                "timeout": timeout,
                "required": required,
                "context": context,
                "timestamp": datetime.now().isoformat()
            }
            
            # 发送问题事件给前端
            yield f"data: {json.dumps(question_event, ensure_ascii=False)}\n\n"
            
            # 显示等待提示
            if question_type == "choice":
                options_text = "、".join(options)
                yield f"🤖 **询问用户**: {question}\n"
                yield f"📋 **选项**: {options_text}\n"
            elif question_type == "confirm":
                yield f"🤖 **需要确认**: {question}\n"
                yield f"📋 **请选择**: 是/否\n"
            else:
                yield f"🤖 **询问用户**: {question}\n"
                yield f"📝 **请输入**: 文本回答\n"
            
            if context:
                yield f"💡 **背景说明**: {context}\n"
            
            yield f"⏰ **等待时间**: {timeout}秒\n"
            yield f"⏳ **等待用户回答中**...\n"
            
            # 等待用户回答
            try:
                answer = await future
                
                # 发送回答接收确认事件
                answer_event = {
                    "event_type": "user_answer_received",
                    "interaction_id": interaction_id,
                    "session_id": self.session_id,
                    "answer": answer,
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(answer_event, ensure_ascii=False)}\n\n"
                
                # 显示收到的回答
                yield f"✅ **收到用户回答**: {answer}\n"
                
                # 根据问题类型进行额外处理
                if question_type == "choice":
                    yield f"🎯 **用户选择了**: {answer}\n"
                elif question_type == "confirm":
                    is_confirmed = answer.lower() in ["yes", "y", "是", "true"]
                    yield f"{'✅ 用户确认' if is_confirmed else '❌ 用户拒绝'}\n"
                else:
                    yield f"📝 **用户输入**: {answer}\n"
                
                yield f"🚀 **继续执行任务**...\n"
                
            except TimeoutError:
                # 发送超时事件
                timeout_event = {
                    "event_type": "interaction_timeout",
                    "interaction_id": interaction_id,
                    "session_id": self.session_id,
                    "timeout": timeout,
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(timeout_event, ensure_ascii=False)}\n\n"
                
                if required:
                    yield f"⏰ **用户交互超时** ({timeout}秒)，任务无法继续\n"
                    raise Exception(f"用户交互超时: {timeout}秒")
                else:
                    # 使用默认值继续
                    default_answer = self._get_default_answer(question_type, options)
                    yield f"⏰ **用户交互超时** ({timeout}秒)，使用默认值继续: {default_answer}\n"
                    
            except Exception as e:
                yield f"❌ **交互异常**: {str(e)}\n"
                if required:
                    raise
                else:
                    yield "🔄 **使用默认处理方式继续**\n"
                    
        except Exception as e:
            logger.error(f"用户交互工具执行失败: {e}")
            yield f"❌ **用户交互失败**: {str(e)}\n"
            if required:
                raise
    
    def _get_default_answer(self, question_type: str, options: List[str]) -> str:
        """获取默认回答"""
        if question_type == "choice" and options:
            return options[0]  # 返回第一个选项
        elif question_type == "confirm":
            return "no"  # 默认否定
        else:
            return "跳过"  # 文本题默认跳过
    
    def set_session_id(self, session_id: str):
        """设置会话ID"""
        self.session_id = session_id
    
    def set_interaction_manager(self, interaction_manager: InteractionManager):
        """设置交互管理器"""
        self.interaction_manager = interaction_manager


# 便捷函数
def create_user_interaction_tool(interaction_manager: InteractionManager, session_id: str) -> UserInteractionTool:
    """创建用户交互工具实例"""
    return UserInteractionTool(interaction_manager=interaction_manager, session_id=session_id)
