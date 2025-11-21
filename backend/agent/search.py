from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import asyncio
import json
from datetime import datetime
import re

from backend.agent import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import BaseLLM, Message, MessageRole, LLMConfig
from backend.llm.llm import OpenAILLM
from backend.tools.base import BaseTool, ToolFunction
from backend.tools.tavily_search import TavilySearch
from backend.tools.terminate import Terminate
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
    
    # 设置默认指令
    instruction: Optional[str] = Field(default=SEARCH_AGENT_AUTO_INSTRUCTION, description="用户自定义prompt")
    
    # 工具实例声明
    tavily_search: Optional[TavilySearch] = Field(default=None, description="Tavily搜索工具实例")
    terminate: Optional[Terminate] = Field(default=None, description="终止工具实例")
    
    # 搜索相关配置
    max_search_rounds: int = Field(default=2, description="最大搜索轮数")
    
    # 搜索历史记录
    search_history: List[Dict[str, Any]] = Field(default_factory=list, description="搜索历史记录")
    current_round: int = Field(default=0, description="当前搜索轮数")
    
    def __init__(self, **kwargs):
        """初始化自主搜索代理"""
        super().__init__(**kwargs)
        
        # 添加搜索工具
        self.tavily_search = TavilySearch()
        self.terminate = Terminate()
        self.add_tool(self.tavily_search)
        self.add_tool(self.terminate)
        
        logger.info(f"SearchAgent {self.agent_id} 初始化完成")
    
    
    async def execute_tools(self, tool_calls):
        """执行工具"""
        logger.info(f"当前工具个数: {len(tool_calls)}")
        tasks = []
        for tool_call in tool_calls:
            function_name = tool_call.function['name']
            if function_name == "terminate":
                arguments = json.loads(tool_call.function['arguments'])
                yield f"\n<TOOL_CALL> {function_name} </TOOL_CALL>\n"
                status = await self.terminate(**arguments)
                yield f"\n<TOOL_RESULT> {status} </TOOL_RESULT>\n"
                # TODO 要不要加状态判断成功、失败
                self.state = AgentState.FINISHED
                return
                
            yield f"\n<TOOL_CALL> {function_name} </TOOL_CALL>\n"
            arguments = json.loads(tool_call.function['arguments'])
            # 创建一个协程来处理异步生成器
            async def collect_tool_result():
                tool_result = []
                async for chunk in self.tavily_search(**arguments):
                    tool_result.append(chunk)
                # 如果只有一个结果，直接返回；否则返回列表
                return tool_result[0] if len(tool_result) == 1 else tool_result
            
            tasks.append(collect_tool_result())
        
        # 如果没有非terminate的工具调用，直接返回
        if not tasks:
            return
        results = await asyncio.gather(*tasks)
        
        messages = [
            Message(
                role=MessageRole.ASSISTANT, content="",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_calls=tool_calls,
                metadata={"current_round": self.current_round}
            )
        ]
        for i, res in enumerate(results):
            cur_content = "\n"
            if isinstance(res, str):
                answer = res
            elif isinstance(res, dict):
                answer = res.get("answer", "")
                for r in res.get("results", []):
                    cur_content += f"[TITLE]: {r.get("title", "")} \n"
                    cur_content += f"[URL]: {r.get("url", "")} \n"
            messages.append(
                Message(
                    role=MessageRole.TOOL, content=answer,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tool_call_id=tool_calls[i].id,
                    metadata={"current_round": self.current_round}
                )
            )
            
            yield f"\n<TOOL_RESULT> {answer} </TOOL_RESULT>\n"
            yield f"\n<TOOL_RESULT_URL> {cur_content} </TOOL_RESULT_URL>\n" 
        self.memory.states[self.agent_id]["tool_result"].extend(results)
        self.memory.states[self.agent_id]["all_history"].extend(messages)

    async def run(self, query: str):
        """执行自主搜索代理的主要逻辑"""
        if not self.llm:
            raise ValueError("LLM未配置，无法执行自主搜索代理")
        
        # 设置状态为运行中
        self.state = AgentState.RUNNING
        self.current_round = 0
        
        # try:
        logger.info(f"开始执行自主搜索：{query}")
        
        messages = [
            Message(
                role=MessageRole.SYSTEM, content=self.instruction, 
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            ),
            Message(
                role=MessageRole.USER, content=SEARCH_AGENT_USER_TEMPLATE.format(user_query=query),
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