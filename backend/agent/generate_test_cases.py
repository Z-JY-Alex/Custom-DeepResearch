
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import asyncio
import json
from datetime import datetime

from backend.agent import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import BaseLLM, Message, MessageRole, LLMConfig
from backend.prompts.test_cases import TEST_CASES_SYSTEM_PROMPT, TEST_CASES_USER_PROMPT



class TestCasesGeneratorAgent(BaseAgent):
    """
    测试用例生成代理：专门用于根据接口文档或功能需求生成全面的测试用例。
    
    功能特性：
    - 分析接口文档和功能需求
    - 生成系统化的测试用例集
    - 覆盖功能、参数、异常、安全、性能等多个维度
    - 提供结构化的测试用例文档
    - 支持多种测试场景设计
    """
    
    # 重新定义基本属性的默认值
    agent_name: str = Field(default="TestCasesGeneratorAgent", description="Agent名称")
    agent_description: str = Field(
        default="测试用例生成代理：专门用于根据接口文档或功能需求生成全面的测试用例。",
        description="Agent描述"
    )
    
    # 默认指令
    # instruction: Optional[str] = Field(
    #     default=TEST_CASES_SYSTEM_PROMPT.format(CURRUENT_TIME=CURRUENT_TIME, WORKDIR=WORKDIR),
    #     description="Agent指令"
    # )
    
    # 工具实例
    # shell_tool: Optional[ShellExecuteTool] = Field(default=None, description="Shell执行工具")

    # 测试用例生成配置
    max_rounds: int = Field(default=80, description="最大执行轮数")
    
    current_round: int = Field(default=0, description="当前执行轮数")
    
    def __init__(self, **kwargs):
        """初始化测试用例生成代理"""
        super().__init__(**kwargs)
        
        if self.instruction is None:
            self.instruction = TEST_CASES_SYSTEM_PROMPT.format(
                CURRENT_TIME=self.current_time, 
                WORKDIR=self.work_dir
            )

        # 初始化工具
        # self.shell_tool = ShellExecuteTool()
        
        # 添加工具到代理
        # self.add_tool(self.shell_tool)
        
        logger.info(f"TestCasesGeneratorAgent {self.agent_id} 初始化完成，包含 {len(self.tools)} 个工具")
        
    
    async def run(self, query: str, context: str = ""):
        """执行测试用例生成任务"""
        if not self.llm:
            raise ValueError("LLM未配置")
        
        # 设置状态
        self.state = AgentState.RUNNING
        self.current_round = 0
        
        logger.info(f"开始执行测试用例生成任务: {query}")
        
        # 初始化消息
        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content=self.memory.states["api_docs"],
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": 0}
            ),
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
                content=TEST_CASES_USER_PROMPT.format(task_description=query),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": 0}
            )
        ]
        
        # 初始化内存状态
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}
        
        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["context"] = context
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []
        
        async for x in self._run():
            yield x