from datetime import datetime
import inspect
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import Field
from loguru import logger
import json
import asyncio
import os

from backend.agent.base import BaseAgent
from backend.agent.schema import AgentState
from backend.llm.base import Message, MessageRole
from backend.tools.plan import PlanningTool
from backend.tools.agent_change import SubAgentExecute
from backend.prompts.plan_ai_test import PLANNER_INSTRUCTION, PLAN_USER_PROMPT
from backend.utils.history import save_history_to_file

CURRUENT_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
WORKDIR = "/data/zhujingyuan/deepresearch"


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
    instruction: str = Field(default=PLANNER_INSTRUCTION.format(CURRUENT_TIME=CURRUENT_TIME, WORKDIR=WORKDIR), \
                                description="用户自定义prompt, 代替base_prompt")
    
    planning_tool: Optional[PlanningTool] = Field(default=None, description="Tavily搜索工具实例")
    agent_choices_tool: Optional[SubAgentExecute] = Field(default=None, description="子代理选择工具实例")
    
    agent_maps: dict

    
    def __init__(self, **kwargs):
        """初始化计划代理"""
        super().__init__(**kwargs)
        
        # 添加计划工具
        self.planning_tool = PlanningTool()
        self.agent_choices_tool = SubAgentExecute(
            llm_config=self.llm_config,
            memory=self.memory,
            artifact_manager=self.artifact_manager,
            agent_pools=self.agent_maps
        )

        self.add_tool(self.planning_tool)
        self.add_tool(self.agent_choices_tool)
    
    # 为了控制PlanAgent 在完成一个子任务后，只保存最后artifact的结果到history中,避免上下文信息过长
    async def execute_tools(self, tool_calls):
        """执行工具调用"""
        logger.info(f"准备执行 {len(tool_calls)} 个工具调用")
        
        # 更新消息历史
        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_calls=tool_calls,
                metadata={"current_round": self.current_round}
            )
        ]
        
        for i, tool_call in enumerate(tool_calls):
            function_name = tool_call.function['name']
            arguments = json.loads(tool_call.function['arguments'])
            
            logger.info(f"执行工具: {function_name}")
            yield f"\n<TOOL_CALL> {function_name} </TOOL_CALL>\n"
            yield f"\n<TOOL_ARGS> {str(arguments)[:100]} </TOOL_ARGS>\n"
            # 根据工具名称获取对应的工具实例
            tool_instance = self.get_tool_by_name(function_name)
            
            if not tool_instance:
                error_msg = f"未找到工具: {function_name}"
                logger.error(error_msg)
                yield f"\n❌ **错误**: {error_msg}\n"
                continue
            
            try:
                cur_tool_res = ""
                yield "\n<TOOL_RESULT>"
                async for chunk in self._tool_reponse(tool_instance(**arguments)):
                    cur_tool_res += chunk
                    yield chunk
                yield "\n</TOOL_RESULT>"
                
                if function_name == "terminate":
                    self.state = AgentState.FINISHED
                    return
                
            except Exception as e:
                cur_tool_res = f"工具执行失败: {str(e)}"
                logger.error(f"{function_name} 执行失败: {e}")
                yield f"\n<TOOL_RESULT> {cur_tool_res} </TOOL_RESULT>\n"
            
            if function_name == "sub_agent_run":
                cur_tool_res = self.artifact_manager.artifacts_content[-1].summary
            
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
        
        messages = [
            Message(
                role=MessageRole.ASSISTANT, content=query,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            ),
            Message(
                role=MessageRole.SYSTEM, content=self.instruction, 
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            ),
            Message(
                role=MessageRole.USER, content=PLAN_USER_PROMPT.format(user_query="分析接口文档，使用pytest+requests+allure 生成测试报告"),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), metadata={"current_round": self.current_round}
            )
        ]
        
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}
        
        self.memory.states["api_docs"] = query
        self.memory.states[self.agent_id]["task"] = query
        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []
        
        async for x in self._run():
            yield x
            
        # 执行完成后保存历史记录
        
            

            
