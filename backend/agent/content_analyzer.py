
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import asyncio
import json
from datetime import datetime

from backend.agent import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import BaseLLM, Message, MessageRole
from backend.prompts.content_analysis import CONTENT_ANALYSIS_SYSTEMP_PROMPT, CONTENT_ANALYSIS_USER_PROMPT
from backend.tools.shell_execute import ShellExecuteTool

CURRUENT_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
WORKDIR = str(Path(__file__).parent.parent.parent.absolute())

class ContentAnalyzerAgent(BaseAgent):
    """
    分析总结代理：专门用于分析和总结信息的智能代理。
    
    功能特性：
    - 读取和分析文件内容
    - 生成结构化的分析报告
    - 提取关键信息和洞察
    - 创建总结文档
    - 支持多种分析模式（摘要、对比、趋势分析等）
    """
    
    # 重新定义基本属性的默认值
    agent_name: str = Field(default="ContentAnalyzerAgent", description="Agent名称")
    agent_description: str = Field(
        default="专门用于分析和总结信息的智能代理，能够读取文件、分析内容并生成结构化报告",
        description="Agent描述"
    )
    
    # 默认指令
    instruction: Optional[str] = Field(
        default=CONTENT_ANALYSIS_SYSTEMP_PROMPT.format(CURRUENT_TIME=CURRUENT_TIME, WORKDIR=WORKDIR),
        description="Agent指令"
    )
    
    # 工具实例
    shell_tool: Optional[ShellExecuteTool] = Field(default=None, description="文件保存工具")


    def __init__(self, **kwargs):
        """初始化分析总结代理"""
        super().__init__(**kwargs)
        
        # 初始化工具
        self.shell_tool = ShellExecuteTool()

        # 添加工具到代理
        self.add_tool(self.shell_tool)
    
    async def run(self, query: str):
        """执行分析任务"""
        if not self.llm:
            raise ValueError("LLM未配置")
    
        
        # 设置状态
        self.state = AgentState.RUNNING
        self.current_round = 0
        
        logger.info(f"开始执行分析任务: {query}")
        
        
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
                content=CONTENT_ANALYSIS_USER_PROMPT.format(query=query),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                metadata={"current_round": 0}
            )
        ]
        
        # 初始化内存状态
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}
        
        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []
        
        async for x in self._run():
            yield x