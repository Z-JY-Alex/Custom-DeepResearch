"""
接口自动化测试工程师Agent：专门用于基于接口文档生成完整的自动化测试用例
"""

from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

from backend.agent import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import BaseLLM, Message, MessageRole, LLMConfig
from backend.llm.llm import OpenAILLM
from backend.tools.base import BaseTool, ToolFunction
from backend.prompts.api_test import API_TEST_SYSTEM_PROMPT, API_TEST_USER_PROMPT
from backend.tools.shell_execute import ShellExecuteTool
from backend.tools.file_operations import FileCreateTool, FileSaveTool, FileReadTool
from backend.tools.terminate import Terminate


class ApiTestEngineerAgent(BaseAgent):
    """
    接口自动化测试工程师Agent：基于接口文档生成完整的自动化测试用例
    
    功能特性：
    - 解析接口文档，识别接口规范和参数
    - 生成pytest + requests自动化测试用例
    - 覆盖正常、异常、边界、安全和业务逻辑等多个维度
    - 支持Allure测试报告生成
    - 自动处理测试数据的预制和清理
    - 支持并发测试和性能测试
    """
    
    # 重新定义基本属性的默认值
    agent_name: str = Field(default="ApiTestEngineerAgent", description="Agent名称")
    agent_description: str = Field(
        default="资深的接口自动化测试工程师，能够基于接口文档生成完整的自动化测试用例，覆盖多个测试维度",
        description="Agent描述"
    )
    
    # 默认指令 - 使用用户提供的prompt
    instruction: Optional[str] = Field(
        default=API_TEST_SYSTEM_PROMPT,
        description="Agent指令"
    )
    
    # 工具实例
    shell_tool: Optional[ShellExecuteTool] = Field(default=None, description="Shell执行工具")  
    
    def __init__(self, **kwargs):
        """初始化接口自动化测试工程师Agent"""
        super().__init__(**kwargs)
        
        # 初始化工具
        self.shell_tool = ShellExecuteTool()
        
        # 添加工具到代理
        self.add_tool(self.shell_tool)
        
        logger.info(f"ApiTestEngineerAgent {self.agent_id} 初始化完成，包含 {len(self.tools)} 个工具")
    
    
    async def run(self, query: str, api_docs: str = ""):
        """执行接口自动化测试工程师的主要逻辑"""
        if not self.llm:
            raise ValueError("LLM未配置")
        
        # 设置状态
        self.state = AgentState.RUNNING
        self.current_round = 0
        
        logger.info(f"开始执行接口自动化测试任务: {query}")
        
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
                content=API_TEST_USER_PROMPT.format(query=query, api_docs=api_docs),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": 0}
            )
        ]
        
        # 初始化内存状态
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}
        
        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["api_docs"] = api_docs
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []
        
        async for x in self._run():
            yield x