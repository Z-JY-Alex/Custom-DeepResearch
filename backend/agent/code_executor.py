
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import asyncio
import json
from datetime import datetime

from backend.agent import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import BaseLLM, Message, MessageRole, LLMConfig

from backend.tools.shell_execute import ShellExecuteTool
from backend.tools.code_execute import CodeExecuteTool
from backend.prompts.code_exec import CODE_EXEC_SYSTEMP_PROMPT, CODE_EXEC_USER_PROMPT

CURRUENT_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
WORKDIR = "/data/zhujingyuan/deepresearch"


class CodeExecutorAgent(BaseAgent):
    """
    文件和代码执行代理：能够自主执行文件操作和代码的智能代理。
    
    功能特性：
    - 通过Shell命令进行文件读取、创建和保存
    - Python代码执行
    - 自主分析任务并选择合适的工具
    - 迭代执行直到任务完成
    """
    
    # 重新定义基本属性的默认值
    agent_name: str = Field(default="FileCodeExecutorAgent", description="Agent名称")
    agent_description: str = Field(
        default="能够自主执行文件操作（读取、创建、保存）和Python代码执行的智能代理",
        description="Agent描述"
    )
    
    # 默认指令
    instruction: Optional[str] = Field(
        default=CODE_EXEC_SYSTEMP_PROMPT.format(CURRUENT_TIME=CURRUENT_TIME, WORKDIR=WORKDIR),
        description="Agent指令"
    )
    
    # 工具实例
    shell_execute_tool: Optional[ShellExecuteTool] = Field(default=None, description="Shell命令执行工具")
    # code_execute_tool: Optional[CodeExecuteTool] = Field(default=None, description="代码执行工具")

    enable_safe_mode: bool = Field(default=True, description="是否启用代码执行安全模式")
    

    def __init__(self, **kwargs):
        """初始化文件代码执行代理"""
        super().__init__(**kwargs)
        
        # 初始化工具
        self.shell_execute_tool = ShellExecuteTool()
        # self.code_execute_tool = CodeExecuteTool()
        
        # 添加工具到代理
        self.add_tool(self.shell_execute_tool)
        # self.add_tool(self.code_execute_tool)
        
        logger.info(f"FileCodeExecutorAgent {self.agent_id} 初始化完成，包含 {len(self.tools)} 个工具")
    
    
    async def run(self, query: str):
        """执行文件代码操作任务"""
        if not self.llm:
            raise ValueError("LLM未配置")
        
        # 设置状态
        self.state = AgentState.RUNNING
        self.current_round = 0
        
        logger.info(f"开始执行任务: {query}")
        
        # 初始化消息
        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content=self.artifact_manager.show(),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": 0}
            ),
            Message(
                role=MessageRole.SYSTEM,
                content=self.instruction,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": 0}
            ),
            Message(
                role=MessageRole.USER,
                content=CODE_EXEC_USER_PROMPT.format(query=query),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": 0}
            )
        ]
        
        # 初始化内存状态
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}
        
        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["execution_history"] = []
        
        
        async for x in self._run():
            yield x