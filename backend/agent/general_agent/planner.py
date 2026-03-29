from datetime import datetime
from typing import List, Optional, AsyncGenerator
from pydantic import Field
from loguru import logger
import json
import asyncio
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
    
    # 支持并行执行独立子任务，同时控制上下文长度（sub_agent_run只保存artifact summary）
    async def execute_tools(self, tool_calls):
        """执行工具调用 - 支持并行执行多个独立子代理"""
        logger.info(f"准备执行 {len(tool_calls)} 个工具调用")

        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_calls=tool_calls,
                metadata={"current_round": self.current_round}
            )
        ]

        # 优先处理 terminate / ask_user（立即执行并返回）
        for i, tool_call in enumerate(tool_calls):
            function_name = tool_call.function['name']
            if function_name in ("terminate", "ask_user"):
                async for chunk in self._execute_single_tool_with_events(i, tool_call, messages):
                    yield chunk
                self.memory.states[self.agent_id]["all_history"].extend(messages)
                self.state = AgentState.FINISHED
                return

        # 分离 parallel 和 sequential 工具
        parallel_tools = []
        sequential_tools = []

        for i, tool_call in enumerate(tool_calls):
            function_name = tool_call.function['name']
            arguments = json.loads(tool_call.function['arguments'])
            tool_instance = self.get_tool_by_name(function_name)
            is_parallel = getattr(tool_instance, 'parallel', False) if tool_instance else False

            if is_parallel:
                parallel_tools.append((i, tool_call, tool_instance, arguments))
            else:
                sequential_tools.append((i, tool_call, tool_instance, arguments))

        if parallel_tools:
            logger.info(f"并行执行 {len(parallel_tools)} 个工具: {[tc.function['name'] for _, tc, _, _ in parallel_tools]}")

        # 记录并行执行前的 artifact 数量
        artifact_count_before = len(self.artifact_manager.artifacts_content) if self.artifact_manager else 0

        # 并行执行 - 真正的实时流式输出
        if parallel_tools:
            # 发送并行分组开始标记（包含每个任务的 call_id 供前端创建容器）
            task_infos = []
            for _, tc, _, args in parallel_tools:
                task_desc = args.get('task', '')[:80] if isinstance(args, dict) else ''
                agent_name = args.get('agent_name', '') if isinstance(args, dict) else ''
                call_id = getattr(tc, 'id', None)
                task_infos.append({"call_id": call_id, "agent_name": agent_name, "task": task_desc})

            yield AgentStreamPayload(
                event_type=AgentEventType.AGENT_CONTENT,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                content="",
                data={"parallel_group": "start", "count": len(parallel_tools), "tasks": task_infos}
            ).to_json()

            async for chunk in self._stream_parallel_tools(parallel_tools, messages):
                yield chunk

            # 发送并行分组结束标记
            yield AgentStreamPayload(
                event_type=AgentEventType.AGENT_CONTENT,
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                session_id=self.session_id,
                current_round=self.current_round,
                content="",
                data={"parallel_group": "end", "count": len(parallel_tools)}
            ).to_json()

        # 并行执行后：替换 sub_agent_run 的消息内容为 artifact summary
        if parallel_tools and self.artifact_manager:
            new_artifacts = self.artifact_manager.artifacts_content[artifact_count_before:]
            if new_artifacts:
                # 为每个并行的 sub_agent_run 分配对应的 artifact summary
                sub_agent_msgs = [
                    (tc, msg) for _, tc, _, _ in parallel_tools
                    for msg in messages
                    if msg.role == MessageRole.TOOL
                    and msg.tool_call_id == tc.id
                    and tc.function['name'] == 'sub_agent_run'
                ]
                for idx, (tc, msg) in enumerate(sub_agent_msgs):
                    if idx < len(new_artifacts) and new_artifacts[idx].summary:
                        msg.content = new_artifacts[idx].summary

        # 串行执行剩余工具
        for i, tool_call, tool_instance, arguments in sequential_tools:
            function_name = tool_call.function['name']
            artifact_before = len(self.artifact_manager.artifacts_content) if self.artifact_manager else 0

            async for chunk in self._execute_single_tool_with_events(i, tool_call, messages, tool_instance, arguments):
                yield chunk

            # sub_agent_run 特殊处理：替换为 artifact summary
            if function_name == "sub_agent_run" and self.artifact_manager:
                new_arts = self.artifact_manager.artifacts_content[artifact_before:]
                if new_arts and new_arts[-1].summary:
                    for msg in messages:
                        if msg.role == MessageRole.TOOL and msg.tool_call_id == tool_call.id:
                            msg.content = new_arts[-1].summary
                            break

            if self.state == AgentState.FINISHED:
                break

        self.memory.states[self.agent_id]["all_history"].extend(messages)

    async def _execute_single_tool_with_events(self, tool_idx, tool_call, messages, tool_instance=None, arguments=None):
        """执行单个工具并生成完整的流式事件"""
        function_name = tool_call.function['name']
        if arguments is None:
            arguments = json.loads(tool_call.function['arguments'])
        if tool_instance is None:
            tool_instance = self.get_tool_by_name(function_name)

        # 工具开始事件
        yield AgentStreamPayload(
            event_type=AgentEventType.TOOL_CALL_START,
            agent_id=self.agent_id, agent_name=self.agent_name,
            session_id=self.session_id, current_round=self.current_round,
            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
        ).to_json()

        # 工具参数事件
        yield AgentStreamPayload(
            event_type=AgentEventType.TOOL_ARGS,
            agent_id=self.agent_id, agent_name=self.agent_name,
            session_id=self.session_id, current_round=self.current_round,
            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
            tool_args=arguments,
        ).to_json()

        if not tool_instance:
            error_msg = f"未找到工具: {function_name}"
            logger.error(error_msg)
            yield AgentStreamPayload(
                event_type=AgentEventType.ERROR,
                agent_id=self.agent_id, agent_name=self.agent_name,
                session_id=self.session_id, current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                error_message=error_msg,
            ).to_json()
            return

        cur_tool_res = ""
        try:
            # 工具结果开始
            yield AgentStreamPayload(
                event_type=AgentEventType.TOOL_RESULT_START,
                agent_id=self.agent_id, agent_name=self.agent_name,
                session_id=self.session_id, current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
            ).to_json()

            # 工具结果内容
            async for chunk in self._tool_reponse(tool_instance(**arguments)):
                if self._is_agent_stream_payload(chunk):
                    yield chunk
                    try:
                        chunk_data = json.loads(chunk.strip())
                        if isinstance(chunk_data, dict) and "content" in chunk_data:
                            cur_tool_res += str(chunk_data.get("content", ""))
                    except (json.JSONDecodeError, AttributeError):
                        pass
                else:
                    chunk_str = str(chunk) if not isinstance(chunk, str) else chunk
                    cur_tool_res += chunk_str

                    if function_name == "ask_user":
                        question_data = json.loads(chunk_str)
                        yield AgentStreamPayload(
                            event_type=AgentEventType.TOOL_RESULT_CONTENT,
                            agent_id=self.agent_id, agent_name=self.agent_name,
                            session_id=self.session_id, current_round=self.current_round,
                            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                            content=question_data.get("question", ""),
                            data=question_data
                        ).to_json()
                    else:
                        yield AgentStreamPayload(
                            event_type=AgentEventType.TOOL_RESULT_CONTENT,
                            agent_id=self.agent_id, agent_name=self.agent_name,
                            session_id=self.session_id, current_round=self.current_round,
                            tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                            content=chunk_str,
                        ).to_json()

            # 工具结果结束
            yield AgentStreamPayload(
                event_type=AgentEventType.TOOL_RESULT_END,
                agent_id=self.agent_id, agent_name=self.agent_name,
                session_id=self.session_id, current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
            ).to_json()

            if function_name in ("terminate", "ask_user"):
                self.state = AgentState.FINISHED
                messages.append(
                    Message(
                        role=MessageRole.TOOL, content=cur_tool_res,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        tool_call_id=tool_call.id,
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
                agent_id=self.agent_id, agent_name=self.agent_name,
                session_id=self.session_id, current_round=self.current_round,
                tool=ToolInfo(name=function_name, call_id=getattr(tool_call, 'id', None)),
                error_message=cur_tool_res,
                data={"traceback": tb},
            ).to_json()

        messages.append(
            Message(
                role=MessageRole.TOOL, content=cur_tool_res,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_call_id=tool_call.id,
                metadata={"current_round": self.current_round}
            )
        )

    async def _stream_parallel_tools(self, parallel_tools, messages):
        """真正的并行流式执行 - 使用 asyncio.Queue 实时输出事件"""
        queue = asyncio.Queue()
        SENTINEL = object()

        def _tag_event(event_json, call_id):
            """给事件注入 parallel_call_id 供前端路由"""
            try:
                data = json.loads(event_json)
                if not data.get('data'):
                    data['data'] = {}
                data['data']['parallel_call_id'] = call_id
                return json.dumps(data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                return event_json

        async def run_single_tool(tool_idx, tool_call, tool_instance, arguments):
            """执行单个工具并将事件推入共享队列"""
            function_name = tool_call.function['name']
            call_id = getattr(tool_call, 'id', None)
            cur_tool_res = ""

            try:
                # TOOL_CALL_START
                await queue.put(_tag_event(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_CALL_START,
                    agent_id=self.agent_id, agent_name=self.agent_name,
                    session_id=self.session_id, current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=call_id),
                ).to_json(), call_id))

                # TOOL_ARGS
                await queue.put(_tag_event(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_ARGS,
                    agent_id=self.agent_id, agent_name=self.agent_name,
                    session_id=self.session_id, current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=call_id),
                    tool_args=arguments,
                ).to_json(), call_id))

                # TOOL_RESULT_START
                await queue.put(_tag_event(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_RESULT_START,
                    agent_id=self.agent_id, agent_name=self.agent_name,
                    session_id=self.session_id, current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=call_id),
                ).to_json(), call_id))

                # 执行工具并流式输出结果
                async for chunk in self._tool_reponse(tool_instance(**arguments)):
                    if self._is_agent_stream_payload(chunk):
                        await queue.put(_tag_event(chunk, call_id))
                        try:
                            chunk_data = json.loads(chunk.strip())
                            if isinstance(chunk_data, dict) and "content" in chunk_data:
                                cur_tool_res += str(chunk_data.get("content", ""))
                        except (json.JSONDecodeError, AttributeError):
                            pass
                    else:
                        chunk_str = str(chunk) if not isinstance(chunk, str) else chunk
                        cur_tool_res += chunk_str
                        await queue.put(_tag_event(AgentStreamPayload(
                            event_type=AgentEventType.TOOL_RESULT_CONTENT,
                            agent_id=self.agent_id, agent_name=self.agent_name,
                            session_id=self.session_id, current_round=self.current_round,
                            tool=ToolInfo(name=function_name, call_id=call_id),
                            content=chunk_str,
                        ).to_json(), call_id))

                # TOOL_RESULT_END
                await queue.put(_tag_event(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_RESULT_END,
                    agent_id=self.agent_id, agent_name=self.agent_name,
                    session_id=self.session_id, current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=call_id),
                ).to_json(), call_id))

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"{function_name} 并行执行失败: {e}\n{tb}")
                cur_tool_res = f"工具执行失败: {str(e)}"
                await queue.put(_tag_event(AgentStreamPayload(
                    event_type=AgentEventType.ERROR,
                    agent_id=self.agent_id, agent_name=self.agent_name,
                    session_id=self.session_id, current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=call_id),
                    error_message=str(e),
                ).to_json(), call_id))
                # 即使失败也发送 TOOL_RESULT_END，让前端能正确更新卡片状态
                await queue.put(_tag_event(AgentStreamPayload(
                    event_type=AgentEventType.TOOL_RESULT_END,
                    agent_id=self.agent_id, agent_name=self.agent_name,
                    session_id=self.session_id, current_round=self.current_round,
                    tool=ToolInfo(name=function_name, call_id=call_id),
                ).to_json(), call_id))

            # sub_agent_run 特殊处理
            if function_name == "sub_agent_run" and self.artifact_manager and self.artifact_manager.artifacts_content:
                cur_tool_res = self.artifact_manager.artifacts_content[-1].summary or cur_tool_res

            messages.append(Message(
                role=MessageRole.TOOL, content=cur_tool_res,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                tool_call_id=tool_call.id,
                metadata={"current_round": self.current_round}
            ))

            # 标记完成
            await queue.put(SENTINEL)

        # 启动所有并行任务
        tasks = [asyncio.create_task(run_single_tool(i, tc, ti, args))
                 for i, tc, ti, args in parallel_tools]

        # 实时从队列读取事件并 yield
        completed = 0
        while completed < len(parallel_tools):
            event = await queue.get()
            if event is SENTINEL:
                completed += 1
            else:
                yield event

        # 确保所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)

    
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
        
            

            
