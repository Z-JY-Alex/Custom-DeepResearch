import traceback
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import asyncio
import json
from datetime import datetime

from backend.agent.base import AgentEventType, AgentStreamPayload, BaseAgent, ToolInfo
from backend.agent.schema import AgentState
from backend.llm.base import Message, MessageRole
from backend.tools.tavily_search import TavilySearch
from backend.prompts.search_agent import SEARCH_AGENT_AUTO_INSTRUCTION, SEARCH_AGENT_USER_TEMPLATE


class SearchAgent(BaseAgent):
    """
    自主搜索代理：能够自主分析问题、制定搜索策略并调用工具执行搜索的智能代理。
    
    功能特性：
    - 深度问题分析和搜索策略制定
    - 自主调用搜索工具
    - 智能决策和迭代搜索
    - 结果质量评估和综合分析
    """
    
    # 重新定义基本属性的默认值
    agent_name: str = Field(default="AutoSearchAgent", description="Agent名称")
    agent_description: str = Field(
        default="能够自主分析问题、制定搜索策略并调用工具执行搜索的智能代理，提供高质量的信息检索和分析服务",
        description="Agent描述"
    )
    
    # 工具实例声明
    tavily_search: Optional[TavilySearch] = Field(default=None, description="Tavily搜索工具实例")
    

    def __init__(self, **kwargs):
        """初始化自主搜索代理"""
        super().__init__(**kwargs)
        
        self.instruction = SEARCH_AGENT_AUTO_INSTRUCTION.format(
            CURRENT_TIME=self.current_time, 
            WORKDIR=self.work_dir,
            session_id=self.session_id
        )
        # 添加搜索工具
        self.tavily_search = TavilySearch()
        self.add_tool(self.tavily_search)
        
        logger.info(f"SearchAgent {self.agent_id} 初始化完成")


    async def run(self, query: str):
        """执行自主搜索代理的主要逻辑"""
        if not self.llm:
            raise ValueError("LLM未配置，无法执行自主搜索代理")
        
        # 设置状态为运行中
        self.state = AgentState.RUNNING
        self.current_round = 0
        
        # logger.info(f"开始执行自主搜索：{query}")
        
        messages = [
            Message(
                role=MessageRole.ASSISTANT, content=self.artifact_manager.show(),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            ),
            Message(
                role=MessageRole.SYSTEM, content=self.instruction, 
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            ),
            Message(
                role=MessageRole.USER, content=SEARCH_AGENT_USER_TEMPLATE.format(user_query=query, session_id=self.session_id, CURRENT_TIME=self.current_time),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            )
        ]
        
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}
        
        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []

        async for x in self._run():
            yield x