from datetime import datetime
from typing import List, Optional, AsyncGenerator
from pydantic import Field
from loguru import logger
import json
import traceback

from backend.agent.general_agent.base import BaseAgent, AgentStreamPayload, ToolInfo, AgentEventType
from backend.agent.schema import AgentState
from backend.llm.base import Message, MessageRole
from backend.tools.plan import PlanningTool
from backend.tools.agent_change import SubAgentExecute
from backend.tools.user_interaction import UserInteractionTool

from backend.prompts.plan_agent import PLANNER_INSTRUCTION


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
    # instruction: str = Field(default=PLANNER_INSTRUCTION.format(CURRUENT_TIME=CURRUENT_TIME, WORKDIR=WORKDIR), \
    #                             description="用户自定义prompt, 代替base_prompt")
    user_interaction_tool: Optional[UserInteractionTool] = Field(default=None, description="用户交互工具")
    planning_tool: Optional[PlanningTool] = Field(default=None, description="Tavily搜索工具实例")
    agent_choices_tool: Optional[SubAgentExecute] = Field(default=None, description="子代理选择工具实例")
    agent_maps: dict

    
    def __init__(self, **kwargs):
        """初始化计划代理"""
        super().__init__(**kwargs)
        
        if self.instruction is None:
            self.instruction = PLANNER_INSTRUCTION.format(
                CURRENT_TIME=self.current_time, 
                WORKDIR=self.work_dir,
                session_id=self.session_id
            )

        # 添加计划工具
        self.planning_tool = PlanningTool(session_id=self.session_id)
        self.agent_choices_tool = SubAgentExecute(
            session_id=self.session_id,
            llm_config=self.llm_config,
            memory=self.memory,
            artifact_manager=self.artifact_manager,
            agent_pools=self.agent_maps
        )
        self.user_interaction_tool = UserInteractionTool()

        self.add_tool(self.planning_tool)
        self.add_tool(self.agent_choices_tool)
        self.add_tool(self.user_interaction_tool)
    
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
            
            ## 工具开始
            tool_call_event = AgentStreamPayload(
                event_type=AgentEventType.TOOL_CALL_START,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
            )
            yield tool_call_event.to_json()

            ## 工具入参(可以隐藏内容)
            tool_args_event = AgentStreamPayload(
                event_type=AgentEventType.TOOL_ARGS,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
                tool_args=arguments,
            )
            yield tool_args_event.to_json()
            
            # 根据工具名称获取对应的工具实例
            tool_instance = self.get_tool_by_name(function_name)
            
            if not tool_instance:
                error_msg = f"未找到工具: {function_name}"
                logger.error(error_msg)
                ## 错误
                yield AgentStreamPayload(
                    event_type=AgentEventType.ERROR,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
                    error_message=error_msg,
                ).to_json()
                continue
            
            try:
                cur_tool_res = ""
                # 结果开始
                ## 工具结果开始
                yield AgentStreamPayload(
                    event_type=AgentEventType.TOOL_RESULT_START,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
                ).to_json()

                ## 工具结果内容
                async for chunk in self._tool_reponse(tool_instance(**arguments)):
                    # 如果 chunk 已经是 AgentStreamPayload 格式，直接透传，避免嵌套
                    if self._is_agent_stream_payload(chunk):
                        yield chunk
                        # 为了记录到消息历史，需要提取内容
                        try:
                            chunk_data = json.loads(chunk.strip())
                            if isinstance(chunk_data, dict) and "content" in chunk_data:
                                cur_tool_res += str(chunk_data.get("content", ""))
                        except (json.JSONDecodeError, AttributeError):
                            pass
                    else:
                        # 确保 chunk 是字符串类型
                        chunk_str = str(chunk) if not isinstance(chunk, str) else chunk
                        cur_tool_res += chunk_str

                        # 特殊处理 ask_user 工具：解析 JSON 并发送 USER_QUESTION 事件
                        if function_name == "ask_user":
                            question_data = json.loads(chunk_str)
                            yield AgentStreamPayload(
                                event_type=AgentEventType.TOOL_RESULT_CONTENT,
                                agent_id=self.agent_id,
                                agent_name=self.agent_name,
                                session_id=self.session_id,
                                current_round=self.current_round,
                                tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
                                content=question_data.get("question", ""),
                                data=question_data
                            ).to_json()
                        else:
                            # 其他工具使用普通的 TOOL_RESULT_CONTENT 事件
                            yield AgentStreamPayload(
                                event_type=AgentEventType.TOOL_RESULT_CONTENT,
                                agent_id=self.agent_id,
                                agent_name=self.agent_name,
                                session_id=self.session_id,
                                current_round=self.current_round,
                                tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
                                content=chunk_str,
                            ).to_json()

                ## 工具结果结束
                yield AgentStreamPayload(
                    event_type=AgentEventType.TOOL_RESULT_END,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
                ).to_json()
                
                if function_name == "terminate" or function_name == "ask_user":
                    self.state = AgentState.FINISHED
                    messages.append(
                        Message(
                            role=MessageRole.TOOL, content=cur_tool_res,
                            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            tool_call_id=tool_calls[i].id,
                            metadata={"current_round": self.current_round}
                        )
                    )
                    return

            except Exception as e:
                cur_tool_res = f"工具执行失败: {str(e)}"
                tb = traceback.format_exc()
                logger.error(f"{function_name} 执行失败: {e}\n{tb}")
                yield AgentStreamPayload(
                    event_type=AgentEventType.ERROR,
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    session_id=self.session_id,
                    current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=getattr(tool_calls[i], 'id', None)),
                    error_message=cur_tool_res,
                    data={"traceback": tb},
                ).to_json()
            
            if function_name == "sub_agent_run" and self.artifact_manager.artifacts_content:
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

    
    async def run(self, messages: List[Message]):
        """执行计划代理的主要逻辑"""
        
        if not self.llm:
            raise ValueError("LLM未配置，无法执行计划代理")
        
        # 设置状态为运行中
        self.state = AgentState.RUNNING
        
        if len(messages) == 1:
            messages.insert(
                0,
                Message(
                    role=MessageRole.SYSTEM, content=self.instruction, 
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                    metadata={"current_round": self.current_round}
                )
            )
        
        if self.agent_id not in self.memory.states:
            self.memory.states[self.agent_id] = {}

        self.memory.states[self.agent_id]["all_history"] = messages
        self.memory.states[self.agent_id]["tool_result"] = []
        
        async for x in self._run():
            yield x
            
        # 执行完成后保存历史记录
        
            

            
