from datetime import datetime
import inspect
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import json
import asyncio

from backend.agent import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import Message, MessageRole
from backend.tools.base import BaseTool, ToolFunction
from backend.tools.plan import PlanningTool
from backend.tools.agent_change import SubAgentExecute
from backend.tools.terminate import Terminate
from backend.prompts.plan_agent import PLANNER_INSTRUCTION, PLAN_USER_PROMPT



class PlanAgent(BaseAgent):
    """
    计划代理：专门负责为复杂任务创建、管理和执行计划的智能代理。
    
    功能特性：
    - 分析复杂任务并分解为可执行的步骤
    - 创建和管理多个计划
    - 跟踪计划执行进度
    - 根据执行情况动态调整计划
    """
    
    # 重新定义基本属性的默认值
    agent_name: str = Field(default="PlanAgent", description="Agent名称")
    agent_description: str = Field(
        default="专门负责任务规划和计划管理的智能代理，能够将复杂任务分解为可执行的步骤序列",
        description="Agent描述"
    )
    
    # 设置默认指令
    instruction: str = Field(default=PLANNER_INSTRUCTION, description="用户自定义prompt, 代替base_prompt")
    
    
    
    planning_tool: Optional[PlanningTool] = Field(default=None, description="Tavily搜索工具实例")
    agent_choices_tool: Optional[SubAgentExecute] = Field(default=None, description="子代理选择工具实例")
    terminate: Optional[Terminate] = Field(default=None, description="终止工具实例")
    
    agent_maps: dict
    tool_maps: dict = Optional[dict]  # 工具名称到工具实例的映射
    
    current_round: int = Field(default=0, description="当前搜索轮数")

    
    def __init__(self, **kwargs):
        """初始化计划代理"""
        super().__init__(**kwargs)
        
        # 添加计划工具
        self.planning_tool = PlanningTool()
        self.agent_choices_tool = SubAgentExecute(agent_pools=self.agent_maps)
        self.terminate = Terminate()

        self.add_tool(self.planning_tool)
        self.add_tool(self.agent_choices_tool)
        self.add_tool(self.terminate)
        self.tool_maps = {tool.name: tool for tool in self.tools}
        
        logger.info(f"PlanAgent {self.agent_id} 初始化完成")
    
    
    async def _tool_reponse(self, func_result: Any) -> AsyncGenerator[Any, None]:
        """兼容 async return 和 async yield 的结果，统一为异步流"""
        if inspect.isasyncgen(func_result):  # 异步生成器
            async for item in func_result:
                yield item
        elif inspect.iscoroutine(func_result):  # 协程对象
            result = await func_result
            yield result
        else:  # 普通值
            yield func_result

    
    async def execute_tools(self, tool_calls):
        """执行工具"""
        messages = [
            Message(
                role=MessageRole.ASSISTANT, content="",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_calls=tool_calls,
                metadata={"current_round": self.current_round}
            )
        ]
        for i, tool_call in enumerate(tool_calls):
            function_name = tool_call.function['name']
            yield f"\n<TOOL_CALL> {function_name} </TOOL_CALL>\n"
            arguments = json.loads(tool_call.function['arguments'])
            yield "\n<TOOL_RESULT>"
            cur_tool_res = ""
            async for chunk in self._tool_reponse(self.tool_maps[function_name](**arguments)):
                cur_tool_res += chunk
                yield chunk
            yield "\n</TOOL_RESULT>"
            if function_name == "terminate":
                self.state = AgentState.FINISHED
                return
                
            messages.append(
                Message(
                    role=MessageRole.TOOL, content=cur_tool_res,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    tool_call_id=tool_calls[i].id,
                    metadata={"current_round": self.current_round}
                )
            )
            
        self.memory.states[self.agent_id]["all_history"].extend(messages)
            
    async def run(self, query: str):
        """执行计划代理的主要逻辑"""
        
        if not self.llm:
            raise ValueError("LLM未配置，无法执行计划代理")
        
        # 设置状态为运行中+
        self.state = AgentState.RUNNING
        self.current_round = 0
        
        messages = [
            Message(
                role=MessageRole.SYSTEM, content=self.instruction, 
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            ),
            Message(
                role=MessageRole.USER, content=PLAN_USER_PROMPT.format(user_query=query),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            )
        ]
        
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}
        
        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []
        
        while self.current_round < 30:
            self.current_round += 1
            logger.info(f"🔄 第 {self.current_round} 轮搜索(PLANING)")
            
            tool_calls = []
            content_parts = ""
            async for chunk in await self.llm.generate(messages=self.memory.states[self.agent_id]["all_history"], tools=self.tools):
                if chunk.content:
                    content_parts += chunk.content
                    yield chunk.content
                if chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)
            
            self.memory.states[self.agent_id]["all_history"].append(
                Message(
                    role=MessageRole.ASSISTANT, content=content_parts, 
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                    metadata={"current_round": self.current_round}
                )
            )
            
            if tool_calls: 
                async for chunk in self.execute_tools(tool_calls=tool_calls):
                    yield chunk

            if self.state == AgentState.FINISHED:
                break


            
